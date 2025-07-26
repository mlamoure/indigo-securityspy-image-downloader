# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Indigo home automation plugin that downloads images from SecuritySpy (or other URLs), with capabilities for:
- Single image downloads from SecuritySpy cameras or arbitrary URLs  
- Multi-camera image stitching (vertical concatenation)
- Animated GIF creation from time-lapse captures
- Image resizing and authentication support

## Plugin Architecture

### Core Components
- **plugin.py**: Main plugin class inheriting from `indigo.PluginBase`
- **Actions.xml**: Defines two main actions - `downloadImage` and `stitchImage`
- **PluginConfig.xml**: SecuritySpy connection settings (IP, port, credentials, SSL)
- **Info.plist**: Plugin metadata and version information

### Key Methods
- `download_image_action()`: Single image download with optional GIF creation (plugin.py:641)
- `stitch_image_action()`: Multi-camera vertical stitching (plugin.py:327)
- `get_image()`: Core HTTP image fetching with authentication (plugin.py:187)
- `stitch_images()`: PIL-based vertical image concatenation (plugin.py:299)
- `camera_list_generator()`: Dynamic camera list for UI dropdowns (plugin.py:486)
- `_discover_cameras()`: Multi-plugin camera discovery (plugin.py:551)
- `_parse_cynical_address()`: Cynical plugin address parser (plugin.py:513)
- `_parse_flyingdiver_address()`: FlyingDiver plugin address parser (plugin.py:529)

### Dependencies
- **requests**: HTTP client for image downloads with digest/basic auth
- **PIL (Pillow)**: Image processing, resizing, stitching, and GIF creation
- **indigo**: Home automation platform API (mocked in development)

## SecuritySpy Integration

The plugin supports multiple SecuritySpy plugin backends:

### Supported Plugins
1. **Cynical SecuritySpy Plugin** (`org.cynic.indigo.securityspy.camera`)
   - Address format: `"Camera Name (camera_number)"`
   - Example: `"Front Door Camera (1)"`
   - Camera number extracted from parentheses

2. **FlyingDiver SecuritySpy Plugin** (`com.flyingdiver.indigoplugin.securityspy`)  
   - Address format: `"{server_id}:{camera_number}"`
   - Example: `"server123:01"`
   - Camera number extracted from colon separator (zero-padding removed)

### Multi-Plugin Support
- **Automatic Discovery**: The plugin automatically discovers cameras from all supported SecuritySpy plugins
- **Unified Interface**: Camera selection menus show cameras from all plugins with plugin identification
- **Fallback Support**: Manual camera numbers (0-15) available when no plugins are installed
- **Address Parsing**: Separate parsers handle each plugin's address format

Camera numbers are used to construct SecuritySpy URLs like `/++image?cameraNum=X`.

## Development Commands

### Installation
```bash
pip install -r requirements.txt
```

### Testing
Run the comprehensive test suite:
```bash
python run_tests.py
```

Or run tests directly with pytest:
```bash
pytest tests/ -v --cov=plugin --cov-report=html
```

### Test Coverage
The test suite covers:
- Plugin initialization and configuration
- Image downloading with various auth methods
- Image stitching and resizing operations
- Animated GIF creation
- Error handling and edge cases
- SecuritySpy camera integration (both Cynical and FlyingDiver plugins)
- Multi-plugin camera discovery and address parsing
- Action handlers and validation

Target coverage: 80%+ with detailed HTML reports in `htmlcov/`

### Deployment
Use the deployment script for Indigo plugins:
```bash
/Users/mike/Mike_Sync_Documents/Programming/mike-local-development-scripts/deploy_indigo_plugin_to_server.sh "SecuritySpy Image Downloader.indigoPlugin"
```

## Key Configuration

### Plugin Settings (PluginConfig.xml)
- SecuritySpy IP/port and SSL settings
- Authentication credentials (login/password)
- Debug logging toggle

### Action Configuration
Both actions support:
- Variable-based or direct path destination files
- Image resizing by maximum width
- Debug log suppression with `hidelog` option

The download action additionally supports:
- GIF creation with configurable duration (2-10 seconds)
- Frame reversal for animated GIFs
- Multiple authentication types for arbitrary URLs

## File Structure Notes

The plugin follows standard Indigo plugin structure:
- `.indigoPlugin/Contents/Info.plist`: Plugin metadata
- `.indigoPlugin/Contents/Server Plugin/`: Python code and XML definitions
- Requirements are duplicated at both root and plugin levels