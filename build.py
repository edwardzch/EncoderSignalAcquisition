import os
import subprocess
import sys

def main():
    print("Starting build process...")
    
    # Check if pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Build command
    # --noconfirm: Overwrite existing build
    # --onedir: Create a one-folder bundle containing an executable
    # --windowed: Do not provide a console window for standard i/o
    # --icon: Set the application icon
    # --add-data: Bundle the icon file inside the executable package
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",          
        "--windowed",        
        "--icon=sincos.ico",
        "--add-data=sincos.ico;.",
        "--name=EncoderSignalAcquisition",
        "main.py"
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        print("\nBuild completed successfully! Check the 'dist' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with error: {e}")

if __name__ == "__main__":
    main()
