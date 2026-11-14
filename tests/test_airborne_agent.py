"""
Unit tests for Airborne Aviation Academy ADK Agent tools and structure.
Verifies ground truth facts, persona rules, and tool outputs.
"""

try:
    import pytest
except ImportError:
    pytest = None
from agent.tools import search_knowledge, book_counseling_session
from agent.prompts import AGENT_INSTRUCTION


def test_agent_instruction_persona() -> None:
    """Verify that agent instruction is properly configured with Piyush and Capt. Navrang Singh."""
    assert "Piyush" in AGENT_INSTRUCTION
    assert "Captain Navrang Singh" in AGENT_INSTRUCTION
    assert "Dwarka" in AGENT_INSTRUCTION
    assert "Rs. 2,70,000" in AGENT_INSTRUCTION
    assert "Rs. 55-65 Lakhs" in AGENT_INSTRUCTION
    assert "₹2,70,000" not in AGENT_INSTRUCTION
    assert "₹55" not in AGENT_INSTRUCTION


def test_search_knowledge_cpl() -> None:
    """Verify ground-truth search for CPL ground school."""
    res = search_knowledge("CPL ground school fees")
    assert "Rs. 2,70,000" in res
    assert "Navrang Singh" in res


def test_search_knowledge_nios() -> None:
    """Verify ground-truth search for NIOS eligibility."""
    res = search_knowledge("NIOS 10+2 eligibility commerce")
    assert "NIOS" in res
    assert "DGCA" in res


def test_book_counseling_session() -> None:
    """Verify counseling booking tool output."""
    res = book_counseling_session("Vikramaditya", "9999888877", "next Friday")
    assert "Vikramaditya" in res
    assert "9999888877" in res
    assert "next Friday" in res
    assert "Dwarka" in res
