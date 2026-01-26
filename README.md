# Lortnoc - Remote Control & Monitoring

Lortnoc is a centralized fleet management and monitoring solution for devices (Raspberry Pi, Servers, IoT).

This project aims to be **simple**, **lightweight**, and **extensible**.

## 🏗 Architecture

The architecture relies on an asynchronous **Publisher/Subscriber** model using **Discord** as a communication bus.

### Dynamic Channel Routing
To ensure scalability and avoid single-channel overload:
1.  The **Client** announces itself on a global HEARTBEAT channel.
2.  The **Client** creates (if necessary) and listens to a dedicated COMMAND channel (named after its normalized client ID, e.g., `client-xyz`).
3.  The **Monitor** dynamically discovers these channels via heartbeats and subscribes to them to send commands.

```mermaid
graph TD
    M[Monitor] -->|Listen| HB[#Heartbeat Channel]
    M -->|Send Commands| CMD[#client-xyz]
    
    C[Client] -->|Post Metrics| HB
    C -.->|Create & Listen| CMD
```

## 📦 Components

### 1. `lortnoc-monitor` (The Brain)
- **Interface**: Web Dashboard (NiceGUI).
- **Role**: Orchestrator, log visualizer, command emitter.
- **Stack**: Python, NiceGUI, discord.py.

### 2. `lortnoc-client` (The Arms)
- **Role**: Lightweight agent running on target machines.
- **Stack**: Python (Standard Lib + psutil + discord.py).
- **Features**:
    - Metrics reporting (CPU, RAM, Temperature, IP).
    - System command execution (Reboot, Shutdown, Shell).
    - Autonomous management of its communication channel.

## 🚀 Installation

### 1. Discord Configuration (Bot)

For Lortnoc to function, the Bot must have permissions to read messages and create channels.

1.  **Create an Application**:
    *   Go to the [Discord Developer Portal](https://discord.com/developers/applications).
    *   Create a "New Application".
2.  **Configure the Bot**:
    *   Menu **Bot** > "Add Bot".
    *   **IMPORTANT**: Under "Privileged Gateway Intents", enable **"Message Content Intent"**.
    *   Copy the **Token**.
3.  **Invite the Bot**:
    *   Menu **OAuth2** > **URL Generator**.
    *   Check **Scopes**: `bot`.
    *   Check **Bot Permissions**: `Administrator` (Recommended to avoid 403 errors) or at least `Manage Channels` + `Read Messages` + `Send Messages` + `Attach Files`.
    *   Use the generated URL to invite the bot to your server.
4.  **Prepare the Server**:
    *   Create a text channel for heartbeats (e.g., `#lortnoc-heartbeat`).
    *   Enable **Developer Mode** in your Discord settings (App Settings > Advanced) to copy the Channel ID.

### 2. Local Configuration (`config/config.json`)
```json
{
  "client_name": "My-Device-01", 
  "heartbeat_interval": 60,
  "discord": {
    "token": "YOUR_BOT_TOKEN",
    "heartbeat_channel_id": "123456789012345678"
  }
}
```
**Configuration Fields :**
* `admin_password` (Monitor Only): Password to access the web dashboard. Default: `admin`.
* `otp_enabled` (Monitor Only): Enable Two-Factor Authentication via Discord channel `#authentication`. Default: `false`.
* `client_name` : Unique identifier for this device. If omitted, the system hostname is used. Ideally use `kebab-case`.
* `log_file` : Path to the log file. Default: `logs/monitor.log`.
* `heartbeat_interval` (optional, default: 300): Check-in frequency in seconds.
* `discord.token`: Your Bot Token (Required).
* `discord.heartbeat_channel_id`: The ID of the centralized channel where all clients post heartbeats.

## 🚀 Quick Start (Production)

### 1. Start the Monitor
The monitor is designed to run in a Docker container.
```bash
cd lortnoc_monitor
./manage.sh build
./manage.sh run
# Access via http://localhost:8080
```

### 2. Install the Client (Systemd)

curl -sL https://raw.githubusercontent.com/pebdev/lortnoc/master/tools/installers/install_client.sh | bash
curl -sL https://raw.githubusercontent.com/pebdev/lortnoc/master/tools/installers/install_monitor.sh | bash

For permanent installation on a target device (e.g., Raspberry Pi):
```bash
cd lortnoc_client
./tools/scripts/install.sh
```

## 💻 Development & Testing

### Test Client with Docker
Useful to quickly test the client logic on your local machine without installing system services.
```bash
cd lortnoc_client
./manage.sh build
./manage.sh run
```

## 🛠 Maintenance (Self-Update)

All updates are centralized and managed via the **Monitor Web Interface**.

*   **Clients**: You can trigger a self-update command from the dashboard for any specific client.
*   **Monitor**: The monitor can also update itself via the interface (rebuilds and restarts the container).


## Todo
- [x] mechanim to identify available updates for both monitor and clients
- [x] add "las activity" timestamp for clients on the monitor dashboard
- [x] provide a way to remove clients from the monitor dashboard
- [ ] add more system metrics (disk usage, network stats, etc.)
- [x] double authentication mechanism for monitor web interface
- [ ] implement encrypted communication between client and monitor
- [ ] security audits and hardening