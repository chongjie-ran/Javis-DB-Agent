#!/usr/bin/env python3
"""
Test runner script for zCloudNewAgentProject

Usage:
    python tests/run_tests.py              # Run all tests
    python tests/run_tests.py --unit      # Run unit tests only
    python tests/run_tests.py --integration # Run integration tests only
    python tests/run_tests.py --coverage  # Run with coverage report
"""
import sys
import os
import argparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def run_tests(test_type="all", coverage=False):
    """Run tests based on type"""
    import pytest
    
    args = [
        "-v",
        "--tb=short"
    ]
    
    if coverage:
        args.extend(["--cov=src", "--cov-report=html", "--cov-report=term"])
    
    if test_type == "unit":
        args.append("tests/unit/")
    elif test_type == "integration":
        args.append("tests/integration/")
    else:
        args.append("tests/")
    
    exit_code = pytest.main(args)
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run zCloudNewAgentProject tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    
    args = parser.parse_args()
    
    if args.unit:
        exit_code = run_tests("unit", args.coverage)
    elif args.integration:
        exit_code = run_tests("integration", args.coverage)
    else:
        exit_code = run_tests("all", args.coverage)
    
    sys.exit(exit_code)
