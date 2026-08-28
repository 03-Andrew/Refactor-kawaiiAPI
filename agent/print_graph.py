import os
import sys
from pathlib import Path

# Ensure project root is first in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
AGENT_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

# Initialize Django environment before importing agent2 if not already initialized
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
import django
django.setup()

from agent2 import APP

def main():
    graph = APP.get_graph()
    
    # 1. Print Graph Flow (ASCII or Mermaid)
    print("\n--- LangGraph Flow ---")
    try:
        graph.print_ascii()
    except Exception:
        # Fallback to Mermaid representation if grandalf is not installed
        print(graph.draw_mermaid())

    # 2. Save graph as PNG
    output_path = AGENT_DIR / "graph.png"
    try:
        png_bytes = graph.draw_mermaid_png()
        output_path.write_bytes(png_bytes)
        print(f"\nSaved graph image to: {output_path}")
    except Exception as e:
        print(f"\nCould not generate PNG (requires internet connection): {e}")

    # 3. If in Jupyter / IPython notebook, display inline
    try:
        from IPython.display import Image, display
        display(Image(output_path.read_bytes()))
    except Exception:
        pass

if __name__ == "__main__":
    main()