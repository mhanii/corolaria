#!/usr/bin/env python3
"""
MariaDB CRUD Verification Tests.

Tests all database operations to verify the migration worked correctly.

Usage:
    DATABASE_TYPE=mariadb python scripts/test_mariadb_crud.py
    
Or with explicit URI:
    MARIADB_URI=mariadb+pymysql://user:pass@host:3306/db python scripts/test_mariadb_crud.py
"""
import os
import sys
import uuid
import time
import threading
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set database type if not set
os.environ.setdefault("DATABASE_TYPE", "mariadb")


def test_database_connection():
    """Test basic database connection."""
    print("\n[TEST] Database Connection")
    print("-" * 40)
    
    from src.infrastructure.database import get_database_connection
    
    try:
        conn = get_database_connection()
        print(f"✓ Connection created: {type(conn).__name__}")
        
        # Simple query
        result = conn.fetchone("SELECT 1 as test", ())
        assert result['test'] == 1, "Query returned unexpected result"
        print("✓ Simple query executed")
        
        return True, conn
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False, None


def test_user_crud(conn):
    """Test user create/read/update/delete operations."""
    print("\n[TEST] User CRUD Operations")
    print("-" * 40)
    
    from src.infrastructure.database.repository_factory import get_user_repository
    
    repo = get_user_repository(conn)
    test_username = f"test_user_{uuid.uuid4().hex[:8]}"
    test_password = "testpassword123"
    
    try:
        # Create
        user = repo.create_user(test_username, test_password, 100)
        assert user is not None, "User creation returned None"
        print(f"✓ Created user: {user.username} (id: {user.id[:8]}...)")
        
        # Read by username
        found = repo.get_by_username(test_username)
        assert found is not None, "User not found by username"
        assert found.id == user.id, "User ID mismatch"
        print(f"✓ Read user by username")
        
        # Read by ID
        found_by_id = repo.get_by_id(user.id)
        assert found_by_id is not None, "User not found by ID"
        print(f"✓ Read user by ID")
        
        # Verify password
        assert repo.verify_password(user, test_password), "Password verification failed"
        print(f"✓ Password verification works")
        
        # Token operations
        initial_tokens = repo.get_token_balance(user.id)
        assert initial_tokens == 100, f"Initial tokens wrong: {initial_tokens}"
        print(f"✓ Token balance: {initial_tokens}")
        
        # Consume tokens
        consumed = repo.consume_tokens(user.id, 10)
        assert consumed, "Token consumption failed"
        assert repo.get_token_balance(user.id) == 90, "Token balance not decremented"
        print(f"✓ Consumed 10 tokens, balance: 90")
        
        # Add tokens
        added = repo.add_tokens(user.id, 20)
        assert added, "Token addition failed"
        assert repo.get_token_balance(user.id) == 110, "Token balance not incremented"
        print(f"✓ Added 20 tokens, balance: 110")
        
        # Test insufficient tokens
        consumed = repo.consume_tokens(user.id, 1000)
        assert not consumed, "Should have failed with insufficient tokens"
        print(f"✓ Insufficient tokens correctly rejected")
        
        return True
        
    except Exception as e:
        print(f"✗ User CRUD failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_conversation_crud(conn):
    """Test conversation/message CRUD operations."""
    print("\n[TEST] Conversation CRUD Operations")
    print("-" * 40)
    
    from src.infrastructure.database.repository_factory import (
        get_user_repository, get_conversation_repository
    )
    
    user_repo = get_user_repository(conn)
    conv_repo = get_conversation_repository(conn)
    
    # Create test user
    test_user = user_repo.create_user(f"conv_test_{uuid.uuid4().hex[:8]}", "password", 50)
    
    try:
        # Create conversation
        conv = conv_repo.create_conversation(test_user.id)
        assert conv is not None, "Conversation creation failed"
        print(f"✓ Created conversation: {conv.id[:8]}...")
        
        # Add user message
        msg1 = conv_repo.add_message(conv.id, "user", "Hello, this is a test message")
        assert msg1 is not None, "User message not created"
        print(f"✓ Added user message")
        
        # Add assistant message with context
        msg2 = conv_repo.add_message(
            conv.id, 
            "assistant", 
            "Hello! I'm here to help.",
            context_json='{"articles": ["art1", "art2"]}'
        )
        assert msg2 is not None, "Assistant message not created"
        print(f"✓ Added assistant message with context")
        
        # Get conversation with messages
        loaded = conv_repo.get_conversation(conv.id, test_user.id)
        assert loaded is not None, "Conversation not found"
        assert len(loaded.messages) == 2, f"Expected 2 messages, got {len(loaded.messages)}"
        print(f"✓ Loaded conversation with {len(loaded.messages)} messages")
        
        # List conversations
        convs = conv_repo.list_conversations(test_user.id)
        assert len(convs) >= 1, "Conversation not in list"
        print(f"✓ Listed {len(convs)} conversation(s)")
        
        # Get last context
        last_ctx = conv_repo.get_last_context(conv.id)
        assert last_ctx is not None, "Last context not found"
        print(f"✓ Retrieved last context")
        
        # Update metadata
        updated = conv_repo.update_metadata(conv.id, {"test_key": "test_value"})
        assert updated, "Metadata update failed"
        metadata = conv_repo.get_metadata(conv.id)
        assert metadata.get("test_key") == "test_value", "Metadata not saved"
        print(f"✓ Metadata updated and retrieved")
        
        # Clear conversation
        cleared = conv_repo.clear_conversation(conv.id, test_user.id)
        assert cleared, "Clear conversation failed"
        loaded_empty = conv_repo.get_conversation(conv.id, test_user.id)
        assert len(loaded_empty.messages) == 0, "Messages not cleared"
        print(f"✓ Cleared conversation messages")
        
        # Delete conversation
        deleted = conv_repo.delete_conversation(conv.id, test_user.id)
        assert deleted, "Delete conversation failed"
        print(f"✓ Deleted conversation")
        
        return True
        
    except Exception as e:
        print(f"✗ Conversation CRUD failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_concurrent_tokens(conn):
    """Test concurrent token operations to verify thread safety."""
    print("\n[TEST] Concurrent Token Operations")
    print("-" * 40)
    
    from src.infrastructure.database.repository_factory import get_user_repository
    from src.infrastructure.database import get_database_connection
    
    # Create user with exactly 100 tokens
    user_repo = get_user_repository(conn)
    test_user = user_repo.create_user(
        f"concurrent_test_{uuid.uuid4().hex[:8]}", 
        "password", 
        100
    )
    
    # 10 threads each trying to consume 15 tokens
    # Only 6 should succeed (6 * 15 = 90, 7 * 15 = 105 > 100)
    success_count = [0]
    lock = threading.Lock()
    
    def consume_tokens():
        # Each thread gets its own connection
        thread_conn = get_database_connection()
        thread_repo = get_user_repository(thread_conn)
        
        if thread_repo.consume_tokens(test_user.id, 15):
            with lock:
                success_count[0] += 1
    
    threads = []
    for i in range(10):
        t = threading.Thread(target=consume_tokens)
        threads.append(t)
    
    # Start all threads
    for t in threads:
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    # Check results
    final_balance = user_repo.get_token_balance(test_user.id)
    expected_successes = 6  # floor(100 / 15)
    
    print(f"  Started with: 100 tokens")
    print(f"  10 threads consuming 15 tokens each")
    print(f"  Successful consumptions: {success_count[0]}")
    print(f"  Final balance: {final_balance}")
    
    # Balance should be non-negative
    if final_balance < 0:
        print(f"✗ RACE CONDITION: Balance went negative!")
        return False
    
    # Verify math
    expected_balance = 100 - (success_count[0] * 15)
    if final_balance != expected_balance:
        print(f"✗ Balance mismatch: expected {expected_balance}, got {final_balance}")
        return False
    
    print(f"✓ Concurrent token operations are thread-safe")
    return True


def test_feedback_survey(conn):
    """Test feedback and survey operations."""
    print("\n[TEST] Feedback & Survey Operations")
    print("-" * 40)
    
    from src.infrastructure.database.repository_factory import (
        get_user_repository, get_conversation_repository,
        get_feedback_repository, get_survey_repository
    )
    from src.domain.models.beta_testing import Feedback, Survey, FeedbackType, ConfigMatrix
    
    user_repo = get_user_repository(conn)
    conv_repo = get_conversation_repository(conn)
    feedback_repo = get_feedback_repository(conn)
    survey_repo = get_survey_repository(conn)
    
    # Create test user and conversation
    test_user = user_repo.create_user(f"beta_test_{uuid.uuid4().hex[:8]}", "password", 50)
    conv = conv_repo.create_conversation(test_user.id)
    msg = conv_repo.add_message(conv.id, "assistant", "Test response")
    
    try:
        # Get actual message ID from database (can't use hardcoded value in MariaDB)
        row = conn.fetchone(
            "SELECT id FROM messages WHERE conversation_id = :p0 ORDER BY id DESC LIMIT 1", 
            (conv.id,)
        )
        message_id = row['id'] if row else None
        assert message_id is not None, "Could not get message ID"
        
        # Create feedback
        config = ConfigMatrix(
            model="gemini-2.0-flash",
            temperature=1.0,
            top_k=10,
            collector_type="rag"
        )
        
        feedback = Feedback(
            user_id=test_user.id,
            message_id=message_id,
            conversation_id=conv.id,
            feedback_type=FeedbackType.LIKE,
            config_matrix=config,
            comment="Great response!"
        )
        
        saved = feedback_repo.save_feedback(feedback)
        assert saved, "Feedback save failed"
        print(f"✓ Saved feedback: {feedback.id[:8]}...")
        
        # Get user feedback
        user_feedback = feedback_repo.get_user_feedback(test_user.id)
        assert len(user_feedback) >= 1, "Feedback not found"
        print(f"✓ Retrieved {len(user_feedback)} feedback item(s)")
        
        # Create survey
        survey = Survey(
            user_id=test_user.id,
            responses=["5", "4", "5", "5", "Great service!"],
            tokens_granted=10
        )
        
        saved = survey_repo.save_survey(survey)
        assert saved, "Survey save failed"
        print(f"✓ Saved survey: {survey.id[:8]}...")
        
        # Get user surveys
        user_surveys = survey_repo.get_user_surveys(test_user.id)
        assert len(user_surveys) >= 1, "Survey not found"
        print(f"✓ Retrieved {len(user_surveys)} survey(s)")
        
        # Count surveys
        count = survey_repo.count_user_surveys(test_user.id)
        assert count >= 1, "Survey count wrong"
        print(f"✓ Survey count: {count}")
        
        return True
        
    except Exception as e:
        print(f"✗ Feedback/Survey test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_checkpointer():
    """Test LangGraph checkpointer with MariaDB."""
    print("\n[TEST] LangGraph Checkpointer")
    print("-" * 40)
    
    try:
        from src.infrastructure.database.checkpointer import get_checkpointer, reset_checkpointer
        
        # Reset to get fresh instance
        reset_checkpointer()
        
        checkpointer = get_checkpointer()
        print(f"✓ Checkpointer created: {type(checkpointer).__name__}")
        
        # Test basic checkpoint operations would require LangGraph graph setup
        # For now just verify it initializes
        
        return True
        
    except Exception as e:
        print(f"✗ Checkpointer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("MariaDB CRUD Verification Tests")
    print("=" * 60)
    print(f"DATABASE_TYPE: {os.getenv('DATABASE_TYPE', 'not set')}")
    print(f"MARIADB_URI: {'set' if os.getenv('MARIADB_URI') else 'not set'}")
    
    results = {}
    
    # Test connection
    success, conn = test_database_connection()
    results["Connection"] = success
    
    if not success:
        print("\n✗ Cannot continue without database connection")
        sys.exit(1)
    
    # Run tests
    results["User CRUD"] = test_user_crud(conn)
    results["Conversation CRUD"] = test_conversation_crud(conn)
    results["Concurrent Tokens"] = test_concurrent_tokens(conn)
    results["Feedback & Survey"] = test_feedback_survey(conn)
    results["Checkpointer"] = test_checkpointer()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n{passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n✓ All tests passed! Migration verified.")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed. Review output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
