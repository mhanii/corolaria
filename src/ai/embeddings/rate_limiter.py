"""
Sliding Window Rate Limiter.

Thread-safe rate limiter using a sliding window algorithm to track
API usage and throttle requests within rate limits.
"""
import threading
import time
from typing import List, Tuple
from src.utils.logger import step_logger


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter for API request throttling.
    
    Tracks request counts within a time window and blocks when
    the limit would be exceeded.
    
    Example:
        limiter = SlidingWindowRateLimiter(max_requests=3000, window_seconds=60.0)
        
        # Before making API call with 500 items:
        limiter.acquire(500)  # Blocks if would exceed limit
    """
    
    def __init__(self, max_requests: int = 3000, window_seconds: float = 60.0):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests allowed in the window (default: 3000)
            window_seconds: Size of sliding window in seconds (default: 60)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: List[Tuple[float, int]] = []  # (timestamp, count)
        self._lock = threading.Lock()
    
    def _prune_expired(self) -> None:
        """Remove entries older than the window. Must hold lock."""
        cutoff = time.time() - self.window_seconds
        self._history = [(ts, count) for ts, count in self._history if ts > cutoff]
    
    def _get_window_total(self) -> int:
        """Get total requests in current window. Must hold lock."""
        self._prune_expired()
        return sum(count for _, count in self._history)
    
    def get_available_capacity(self) -> int:
        """
        Calculate remaining capacity in current window.
        
        Returns:
            Number of requests that can be made without exceeding limit
        """
        with self._lock:
            used = self._get_window_total()
            return max(0, self.max_requests - used)
    
    def acquire(self, count: int, timeout: float = 300.0) -> bool:
        """
        Block until capacity is available, then record usage.
        
        Args:
            count: Number of requests to acquire
            timeout: Maximum seconds to wait (default: 5 minutes)
            
        Returns:
            True if acquired, False if timeout exceeded
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                available = self.max_requests - self._get_window_total()
                
                if count <= available:
                    # Capacity available - record and return
                    self._history.append((time.time(), count))
                    step_logger.debug(
                        f"[RateLimiter] Acquired {count} slots. "
                        f"Window usage: {self._get_window_total()}/{self.max_requests}"
                    )
                    return True
                
                # Calculate wait time until oldest entry expires
                if self._history:
                    oldest_ts = self._history[0][0]
                    wait_until_expire = (oldest_ts + self.window_seconds) - time.time()
                else:
                    wait_until_expire = 0.1
            
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                step_logger.warning(f"[RateLimiter] Timeout waiting for {count} slots")
                return False
            
            # Wait for capacity
            wait_time = min(wait_until_expire + 0.1, timeout - elapsed)
            if wait_time > 0:
                step_logger.info(
                    f"[RateLimiter] Rate limit reached. Waiting {wait_time:.1f}s for capacity..."
                )
                time.sleep(wait_time)
    
    def record(self, count: int) -> None:
        """
        Record that `count` items were processed (without blocking).
        
        Use this when you want to track usage without blocking,
        e.g., for already-in-flight requests.
        
        Args:
            count: Number of requests to record
        """
        with self._lock:
            self._history.append((time.time(), count))
    
    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        with self._lock:
            self._prune_expired()
            total = sum(count for _, count in self._history)
            return {
                "window_seconds": self.window_seconds,
                "max_requests": self.max_requests,
                "current_usage": total,
                "available": self.max_requests - total,
                "entries_in_window": len(self._history)
            }
