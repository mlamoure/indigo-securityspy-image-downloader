#!/usr/bin/env python3
"""
Test runner script for SecuritySpy Image Downloader plugin.

This script sets up the test environment and runs the test suite with
proper coverage reporting.
"""

import sys
import os
import subprocess
from pathlib import Path

def main():
    """Run the test suite with coverage reporting."""
    # Get the project root directory
    project_root = Path(__file__).parent
    
    # Add the plugin path to Python path so tests can import the plugin
    plugin_path = project_root / "SecuritySpy Image Downloader.indigoPlugin" / "Contents" / "Server Plugin"
    sys.path.insert(0, str(plugin_path))
    
    # Change to project directory
    os.chdir(project_root)
    
    # Install test requirements if needed
    print("Installing test requirements...")
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-r", "tests/test_requirements.txt"
    ], check=True)
    
    # Run tests with pytest
    print("Running test suite...")
    result = subprocess.run([
        sys.executable, "-m", "pytest", 
        "tests/",
        "-v",
        "--cov=plugin",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--tb=short"
    ])
    
    if result.returncode == 0:
        print("\n✅ All tests passed!")
        print("📊 Coverage report generated in htmlcov/index.html")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()