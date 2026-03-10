"""
GCHI Dominance Engine — CSV Validator (Page 1)
Redirects to the main app.py logic for backward compatibility.
"""
import os
import sys
import importlib

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import and run the main app
import app
app.main()
