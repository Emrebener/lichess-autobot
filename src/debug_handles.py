"""
Handle Leak Diagnostic Tool
Monitors Windows GDI/USER object usage and Qt timer creation
"""

import psutil
import os
import sys
import time
import atexit
import ctypes
from functools import wraps
from pathlib import Path
from collections import defaultdict

# Windows API for GDI/USER object counts - need proper argument types
GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
GetCurrentProcess.restype = ctypes.c_void_p

GetGuiResources = ctypes.windll.user32.GetGuiResources
GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
GetGuiResources.restype = ctypes.c_uint

GR_GDIOBJECTS = 0
GR_USEROBJECTS = 1
GR_GDIOBJECTS_PEAK = 2
GR_USEROBJECTS_PEAK = 4

def get_gdi_objects():
    """Get current GDI object count"""
    return GetGuiResources(GetCurrentProcess(), GR_GDIOBJECTS)

def get_user_objects():
    """Get current USER object count"""
    return GetGuiResources(GetCurrentProcess(), GR_USEROBJECTS)

# Log file
LOG_FILE = Path(__file__).parent.parent / "handle_debug.log"
_log_file = None

def _log(msg: str):
    """Write to log file"""
    global _log_file
    if _log_file is None:
        _log_file = open(LOG_FILE, 'w', buffering=1)  # Line buffered
    _log_file.write(f"{time.time():.3f} {msg}\n")

def get_handle_count():
    """Get the current number of handles for this process"""
    process = psutil.Process(os.getpid())
    return process.num_handles()

# Store initial counts
_initial_handles = None
_initial_gdi = None
_initial_user = None
_stylesheet_counts = defaultdict(int)
_stylesheet_gdi_increases = defaultdict(int)
_stylesheet_user_increases = defaultdict(int)

def init_handle_tracking():
    """Initialize handle tracking"""
    global _initial_handles, _initial_gdi, _initial_user
    _initial_handles = get_handle_count()
    _initial_gdi = get_gdi_objects()
    _initial_user = get_user_objects()
    _log(f"Initial: handles={_initial_handles}, GDI={_initial_gdi}, USER={_initial_user}")
    print(f"[HANDLES] Initial: handles={_initial_handles}, GDI={_initial_gdi}, USER={_initial_user}")
    print(f"[HANDLES] Logging to {LOG_FILE}")
    
    # Register exit handler to print summary
    atexit.register(print_final_summary)

def print_final_summary():
    """Print summary when program exits"""
    print("\n" + "="*70)
    print("TIMER CREATION SUMMARY")
    print("="*70)
    
    print(f"\nTotal timers created: {_timer_count}")
    print("\nTimers by source:")
    sorted_sources = sorted(_timer_sources.items(), key=lambda x: x[1], reverse=True)[:15]
    for source, count in sorted_sources:
        print(f"  {source}: {count} timers")
    
    print("\n" + "="*70)
    print("OBJECT LEAK SUMMARY - TOP OFFENDERS")
    print("="*70)
    
    # Sort by USER object increases (the real problem for Window Manager)
    sorted_by_user = sorted(_stylesheet_user_increases.items(), key=lambda x: x[1], reverse=True)[:15]
    
    print("\nBy USER object increases (Window Manager objects - THE LEAK):")
    for widget, user_inc in sorted_by_user:
        calls = _stylesheet_counts[widget]
        gdi_inc = _stylesheet_gdi_increases[widget]
        print(f"  {widget}: +{user_inc} USER, +{gdi_inc} GDI from {calls} calls")
    
    print("\nBy GDI object increases:")
    sorted_by_gdi = sorted(_stylesheet_gdi_increases.items(), key=lambda x: x[1], reverse=True)[:15]
    for widget, gdi_inc in sorted_by_gdi:
        calls = _stylesheet_counts[widget]
        user_inc = _stylesheet_user_increases[widget]
        print(f"  {widget}: +{gdi_inc} GDI, +{user_inc} USER from {calls} calls")
    
    print("\nBy call count:")
    sorted_by_calls = sorted(_stylesheet_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    for widget, calls in sorted_by_calls:
        gdi_inc = _stylesheet_gdi_increases[widget]
        user_inc = _stylesheet_user_increases[widget]
        print(f"  {widget}: {calls} calls (+{gdi_inc} GDI, +{user_inc} USER)")
    
    final_gdi = get_gdi_objects()
    final_user = get_user_objects()
    print(f"\nFinal: GDI={final_gdi} (+{final_gdi - _initial_gdi}), USER={final_user} (+{final_user - _initial_user})")
    print("="*70)


# Monkey-patch PyQt6 to track setStyleSheet calls
_original_setStyleSheet = None
_original_startTimer = None
_timer_count = 0
_timer_sources = defaultdict(int)

def patch_qt_for_tracking():
    """Patch Qt widgets to track setStyleSheet and startTimer calls"""
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtCore import QObject
    
    global _original_setStyleSheet, _original_startTimer, _timer_count
    _original_setStyleSheet = QWidget.setStyleSheet
    _original_startTimer = QObject.startTimer
    
    def tracked_startTimer(self, interval, timerType=None):
        global _timer_count
        _timer_count += 1
        
        class_name = self.__class__.__name__
        _timer_sources[class_name] += 1
        
        if _timer_count % 100 == 0:  # Log every 100 timers
            _log(f"TIMER #{_timer_count}: {class_name} (interval={interval}ms)")
            print(f"[TIMER] Total timers created: {_timer_count}")
        
        if timerType is not None:
            return _original_startTimer(self, interval, timerType)
        else:
            return _original_startTimer(self, interval)
    
    QObject.startTimer = tracked_startTimer
    
    def tracked_setStyleSheet(self, stylesheet):
        class_name = self.__class__.__name__
        
        # Get parent hierarchy for better context
        parent = self.parent()
        if parent:
            grandparent = parent.parent()
            if grandparent:
                key = f"{grandparent.__class__.__name__}.{parent.__class__.__name__}.{class_name}"
            else:
                key = f"{parent.__class__.__name__}.{class_name}"
        else:
            key = class_name
        
        _stylesheet_counts[key] += 1
        
        # Check GDI/USER objects before/after
        gdi_before = get_gdi_objects()
        user_before = get_user_objects()
        
        result = _original_setStyleSheet(self, stylesheet)
        
        gdi_after = get_gdi_objects()
        user_after = get_user_objects()
        
        gdi_diff = gdi_after - gdi_before
        user_diff = user_after - user_before
        
        if gdi_diff > 0:
            _stylesheet_gdi_increases[key] += gdi_diff
        if user_diff > 0:
            _stylesheet_user_increases[key] += user_diff
            
        if gdi_diff > 0 or user_diff > 0:
            _log(f"LEAK: {key} +{gdi_diff} GDI, +{user_diff} USER (call #{_stylesheet_counts[key]})")
        
        return result
    
    QWidget.setStyleSheet = tracked_setStyleSheet
    print("[HANDLES] setStyleSheet tracking enabled (monitoring GDI/USER objects)")


def start_monitoring(interval: float = 1.0):
    """Start a background thread that monitors GDI/USER object count"""
    import threading
    
    def monitor():
        last_gdi = get_gdi_objects()
        last_user = get_user_objects()
        last_print = time.time()
        
        while True:
            time.sleep(interval)
            gdi = get_gdi_objects()
            user = get_user_objects()
            now = time.time()
            
            _log(f"MONITOR: GDI={gdi}, USER={user}")
            
            # Print on changes or every 2 seconds
            gdi_diff = gdi - last_gdi
            user_diff = user - last_user
            
            if abs(gdi_diff) > 10 or abs(user_diff) > 10 or now - last_print > 2:
                print(f"[OBJECTS] GDI={gdi} (Δ{gdi_diff:+d}), USER={user} (Δ{user_diff:+d})")
                last_print = now
            
            last_gdi = gdi
            last_user = user
            
            # Critical warning - USER object limit is typically 10,000
            if user > 9000:
                print(f"\n[CRITICAL] USER objects: {user} - ABOUT TO CRASH!")
                print_final_summary()
    
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()


if __name__ == "__main__":
    init_handle_tracking()
    print(f"GDI objects: {get_gdi_objects()}")
    print(f"USER objects: {get_user_objects()}")
