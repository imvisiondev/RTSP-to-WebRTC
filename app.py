import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp
import yaml
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer

# --------- config models ---------
@dataclass
class StreamCfg:
    name: str
    rtsp: str
    whip_url: str
    meta: Dict[str, Any] = field(default_factory=dict)  # <- per-stream one-time payload

@dataclass
class AppCfg:
    streams: List[StreamCfg]
    ice_servers: List[Dict[str, Any]]
    ffmpeg_options: Dict[str, str]
    retry_initial_backoff_seconds: int = 2
    retry_max_backoff_seconds: int = 30

def load_cfg(path: str) -> AppCfg:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    streams = []
    for s in raw["streams"]:
        streams.append(StreamCfg(
            name=s["name"],
            rtsp=s["rtsp"],
            whip_url=s["whip_url"],
            meta=s.get("meta", {})  # optional
        ))
    return AppCfg(
        streams=streams,
        ice_servers=raw.get("ice_servers", []),
        ffmpeg_options=raw.get("ffmpeg_options", {}),
        retry_initial_backoff_seconds=int(raw.get("retry_initial_backoff_seconds", 2)),
        retry_max_backoff_seconds=int(raw.get("retry_max_backoff_seconds", 30)),
    )

# --------- WHIP publish logic ---------
async def publish_one(stream: StreamCfg, appcfg: AppCfg):
    """
    Pull RTSP -> publish via WHIP to Box #2 (your Python WHIP server).
    Sends a one-time 'meta' DataChannel payload on connect (and on reconnect).
    Reconnects on failure with exponential backoff.
    """
    backoff = appcfg.retry_initial_backoff_seconds

    while True:
        pc: Optional[RTCPeerConnection] = None
        player: Optional[MediaPlayer] = None
        session: Optional[aiohttp.ClientSession] = None
        try:
            print(f"[INFO] [{stream.name}] starting publisher -> {stream.whip_url}", file=sys.stderr)

            # Build ICE config
            ice = RTCConfiguration([RTCIceServer(**srv) for srv in appcfg.ice_servers])

            # Ingest RTSP via FFmpeg-backed MediaPlayer (PyAV)
            player = MediaPlayer(stream.rtsp, options=appcfg.ffmpeg_options)

            pc = RTCPeerConnection(ice)

            # ---- One-time metadata channel (created BEFORE createOffer) ----
            meta_channel = pc.createDataChannel("meta")

            @meta_channel.on("open")
            def _on_meta_open():
                try:
                    payload = {
                        "name": stream.name,
                        "rtsp": stream.rtsp,          # optional; remove if sensitive
                        "ts": time.time(),
                        **(stream.meta or {}),        # merge user-provided meta
                    }
                    meta_channel.send(json.dumps(payload))
                    print(f"[INFO] [{stream.name}] sent meta once")
                except Exception as e:
                    print(f"[WARN] [{stream.name}] meta send error: {e}", file=sys.stderr)

            # Attach tracks if present
            if player.video:
                pc.addTrack(player.video)
            if player.audio:
                pc.addTrack(player.audio)

            # Non-trickle offer (compatible with WHIP-style handlers)
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)

            # POST SDP to WHIP endpoint
            headers = {"Content-Type": "application/sdp"}
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            resp = await session.post(stream.whip_url, data=pc.localDescription.sdp, headers=headers)
            if resp.status not in (200, 201):
                text = await resp.text()
                raise RuntimeError(f"WHIP POST failed: {resp.status} {text}")

            answer_sdp = await resp.text()
            await pc.setRemoteDescription(RTCSessionDescription(answer_sdp, "answer"))

            print(f"[INFO] [{stream.name}] publishing established.", file=sys.stderr)
            backoff = appcfg.retry_initial_backoff_seconds  # reset backoff on success

            # Keep alive until failed / cancelled
            await asyncio.Future()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[WARN] [{stream.name}] publish loop error: {e}", file=sys.stderr)
        finally:
            # Cleanup
            try:
                if player:
                    await player.stop()
            except Exception:
                pass
            try:
                if pc:
                    await pc.close()
            except Exception:
                pass
            try:
                if session:
                    await session.close()
            except Exception:
                pass

        # Backoff before reconnect
        print(f"[INFO] [{stream.name}] reconnecting in {backoff}s...", file=sys.stderr)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, appcfg.retry_max_backoff_seconds)

async def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    appcfg = load_cfg(cfg_path)

    tasks = [asyncio.create_task(publish_one(s, appcfg)) for s in appcfg.streams]

    # Run forever, cancel cleanly on Ctrl+C
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
