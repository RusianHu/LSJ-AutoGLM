"""
Phone Agent - An AI-powered phone automation framework.

This package provides tools for automating Android and iOS phone interactions
using AI models for visual understanding and decision making.
"""

from phone_agent.agent import PhoneAgent
from phone_agent.agent_ios import IOSPhoneAgent

__version__ = "1.0.2"
__all__ = ["PhoneAgent", "IOSPhoneAgent"]
