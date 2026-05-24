import os
import sys
import subprocess

if __name__ == "__main__":
    # Resolve paths relative to workspace root
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    app_path = os.path.join(frontend_dir, "app.py")
    
    # Set PYTHONPATH to include backend for configurations and utilities
    backend_dir = os.path.join(root_dir, "backend")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{backend_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"
    
    print(f"🏦 Launching Automated Reconciliation Engine Streamlit Portal...")
    print(f"📂 Entry Point: {app_path}")
    print(f"🚀 Running dev server at http://localhost:8501...")
    
    try:
        # Run streamlit command programmatically
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", app_path, "--server.port", "8501"],
            cwd=frontend_dir,
            env=env,
            check=True
        )
    except KeyboardInterrupt:
        print("\n👋 Streamlit operator portal stopped.")
    except Exception as e:
        print(f"❌ Failed to start Streamlit: {e}")
        sys.exit(1)
