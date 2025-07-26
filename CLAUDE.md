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
- `download_image_action()`: Single image download with optional GIF creation (plugin.py:383)
- `stitch_image_action()`: Multi-camera vertical stitching (plugin.py:214)
- `get_image()`: Core HTTP image fetching with authentication (plugin.py:125)
- `stitch_images()`: PIL-based vertical image concatenation (plugin.py:187)
- `camera_list_generator()`: Dynamic camera list for UI dropdowns (plugin.py:351)

### Dependencies
- **requests**: HTTP client for image downloads with digest/basic auth
- **PIL (Pillow)**: Image processing, resizing, stitching, and GIF creation
- **indigo**: Home automation platform API (mocked in development)

## SecuritySpy Integration

The plugin integrates with both:
1. **SecuritySpy cameras**: Uses camera numbers to construct URLs like `/++image?cameraNum=X`
2. **Cynical SecuritySpy plugin**: Automatically discovers camera devices with filter `org.cynic.indigo.securityspy.camera`

Camera numbers are extracted from device addresses using pattern `(camera_num)`.

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
- SecuritySpy camera integration
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