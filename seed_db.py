#!/usr/bin/env python3
"""
Airborne Aviation Vector DB Seeder Script
Populates Supabase vector database with detailed knowledge of Airborne's 11 core courses.
"""

import rag

if __name__ == "__main__":
    print("Starting Airborne Aviation Vector Knowledge Base Seeding...")
    rag.seed_airborne_knowledge()
