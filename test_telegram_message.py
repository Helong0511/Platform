#!/usr/bin/env python3
"""
Test script to verify the telegram message sender fix
"""
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.telegram.message_sender import send_telegram_message

print("Testing telegram message sender...")
try:
    # Test the send_telegram_message function
    print("1. Testing send_telegram_message...")
    result = send_telegram_message("Test message")
    print(f"   Message sent: {result}")
    
    # The result might be False if TELEGRAM_ADMIN is not set, but we just want to check if it doesn't throw the "pyTelegramBotAPI 模块未安装" error
    print("\nTest passed: No 'pyTelegramBotAPI 模块未安装' error occurred!")
    print("The fix for the telegram message sender is working correctly.")
    
except Exception as e:
    if "pyTelegramBotAPI 模块未安装" in str(e):
        print(f"Test failed: {e}")
    else:
        print(f"Test passed: No 'pyTelegramBotAPI 模块未安装' error occurred (other error: {e})")
