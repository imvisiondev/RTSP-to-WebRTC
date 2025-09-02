# RTSP to WebRTC

This script is a Python-based application that forwards RTSP streams to a WebRTC-HTTP Ingestion Protocol (WHIP) endpoint. It effectively acts as a bridge, converting an RTSP stream into a WebRTC stream and pushing it to a remote server.

## What it is for

This tool is useful in scenarios where you have IP cameras or other devices that expose an RTSP stream on a local network, and you want to make this stream accessible to a remote WebRTC server without exposing the RTSP port to the public internet. This avoids the need for static IP addresses, complex firewall rules, or VPNs at the camera's location.

The script is designed to be run on a machine within the same local network as the RTSP stream source.

## How it works

The application uses the `aiortc` library to handle WebRTC communication and `MediaPlayer` (backed by PyAV and FFmpeg) to consume the RTSP stream.

For each stream defined in the configuration, the script:
1. Connects to the local RTSP stream.
2. Creates a WebRTC peer connection.
3. Initiates a WHIP connection by sending an SDP offer to the configured WHIP endpoint.
4. Once the connection is established, it forwards the video and/or audio tracks from the RTSP stream over WebRTC.
5. It also sends a one-time metadata payload over a WebRTC data channel upon connection.
6. In case of connection failure, it automatically attempts to reconnect with an exponential backoff strategy.

## Features

- **RTSP to WebRTC:** Converts standard RTSP streams to WebRTC.
- **WHIP Support:** Pushes streams to a WHIP-compatible server.
- **Resilient:** Automatically reconnects on failure with exponential backoff.
- **Metadata Channel:** Sends a `meta` JSON payload on a data channel upon connection, allowing you to pass stream-specific information.
- **Concurrent:** Can handle multiple streams concurrently using `asyncio`.
- **Configurable:** All stream and server settings are managed through a YAML configuration file.

## Dependencies

- `aiortc`
- `aiohttp`
- `PyYAML`
- `PyAV` (and its underlying FFmpeg libraries)

## Configuration

The application is configured via a YAML file (e.g., `config_example.yaml`). The default configuration file is `config.yaml`.

The configuration file should have the following structure:

```yaml
# List of ICE servers for WebRTC NAT traversal
ice_servers:
  - urls: "stun:stun.l.google.com:19302"

# Default FFmpeg options for the MediaPlayer
ffmpeg_options:
  # See aiortc documentation for available options
  rtsp_transport: "tcp"

# Retry backoff strategy (in seconds)
retry_initial_backoff_seconds: 2
retry_max_backoff_seconds: 30

# List of streams to forward
streams:
  - name: "camera-1"
    rtsp: "rtsp://user:pass@192.168.1.100/stream1"
    whip_url: "http://your-whip-server.com/whip/endpoint1"
    meta:
      # Optional one-time payload to send on the 'meta' data channel
      location: "Lobby"
      camera_id: "cam-001"

  - name: "camera-2"
    rtsp: "rtsp://192.168.1.101/stream2"
    whip_url: "http://your-whip-server.com/whip/endpoint2"
```

## Usage

1.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
    
2.  Create a configuration file (e.g., `config_example.yaml`).

3.  Run the script, passing the path to your configuration file as an argument:
    ```bash
    python app.py config.yaml
    ```
    If no path is provided, it will look for `config.yaml` in the current directory.
