import os
import sys
import platform

def build_executable():
    """
    Build the executable using PyInstaller
    """
    try:
        import PyInstaller.__main__
    except ImportError:
        print("PyInstaller not found. Installing...")
        os.system(f"{sys.executable} -m pip install pyinstaller")
        import PyInstaller.__main__
    
    print("Building executable...")
    
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_py_path = os.path.join(script_dir, 'main.py')
    
    if not os.path.exists(main_py_path):
        print(f"Error: {main_py_path} does not exist!")
        return
    
    # Build PyInstaller command
    pyinstaller_args = [
        main_py_path,
        '--name=OSD',
        '--onefile',
        '--windowed',
        '--clean',
    ]
    
    # Add icon if it exists
    icon_file = "./static/img/download.png" if platform.system() == "Windows" else "icon.icns"
    icon_path = os.path.join(script_dir, icon_file)
    if os.path.exists(icon_path):
        pyinstaller_args.append(f'--icon={icon_path}')
    else:
        print(f"Warning: Icon file {icon_path} not found. Building without custom icon.")
    
    PyInstaller.__main__.run(pyinstaller_args)
    
    print(f"Build complete! Executable can be found in the dist folder.")

if __name__ == "__main__":
    build_executable()