"""Redis caching layer for MattasMCP services"""

import os
import json
import hashlib
import logging
import time
from typing import Any, Optional, Dict, Callable, TypeVar, Union
from functools import wraps
from datetime import timedelta
from dataclasses import dataclass, field
import redis
from redis import Redis, ConnectionPool, RedisError
from redis.connection import SSLConnection
import ssl

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class CacheStats:
    """Cache performance metrics"""
    hits: int = 0
    misses: int = 0
    errors: int = 0
    total_requests: int = 0
    hit_time_sum: float = 0.0
    miss_time_sum: float = 0.0
    last_reset: float = field(default_factory=time.time)
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests
    
    @property
    def miss_rate(self) -> float:
        """Calculate cache miss rate"""
        if self.total_requests == 0:
            return 0.0
        return self.misses / self.total_requests
    
    @property
    def avg_hit_time(self) -> float:
        """Average time for cache hits in milliseconds"""
        if self.hits == 0:
            return 0.0
        return (self.hit_time_sum / self.hits) * 1000
    
    @property
    def avg_miss_time(self) -> float:
        """Average time for cache misses in milliseconds"""
        if self.misses == 0:
            return 0.0
        return (self.miss_time_sum / self.misses) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary"""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'errors': self.errors,
            'total_requests': self.total_requests,
            'hit_rate': self.hit_rate,
            'miss_rate': self.miss_rate,
            'avg_hit_time_ms': self.avg_hit_time,
            'avg_miss_time_ms': self.avg_miss_time,
            'uptime_seconds': time.time() - self.last_reset
        }
    
    def reset(self):
        """Reset all statistics"""
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.total_requests = 0
        self.hit_time_sum = 0.0
        self.miss_time_sum = 0.0
        self.last_reset = time.time()


@dataclass
class CacheConfig:
    """Configuration for cache behavior"""
    ttl: int = 300  # Default 5 minutes
    key_prefix: str = ""
    serialize_json: bool = True  # Use JSON serialization
    compress: bool = False  # Future: add compression support
    version: str = "v1"  # Cache version for key generation
    
    def get_ttl_seconds(self) -> int:
        """Get TTL in seconds"""
        return self.ttl


class RedisCache:
    """Redis cache manager with SSL support and connection pooling"""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        use_ssl: bool = True,
        ssl_cert_reqs: str = 'required',
        max_connections: int = 50,
        connection_timeout: int = 5,
        socket_timeout: int = 5,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30
    ):
        """
        Initialize Redis cache manager
        
        Args:
            host: Redis host (defaults to REDIS_HOST env var)
            port: Redis port (defaults to REDIS_SSL_PORT env var)
            password: Redis password (defaults to REDIS_KEY env var)
            use_ssl: Whether to use SSL connection
            ssl_cert_reqs: SSL certificate requirements
            max_connections: Maximum number of connections in pool
            connection_timeout: Connection timeout in seconds
            socket_timeout: Socket timeout in seconds
            retry_on_timeout: Whether to retry on timeout
            health_check_interval: Health check interval in seconds
        """
        self.host = host or os.getenv('REDIS_HOST')
        self.port = int(port or os.getenv('REDIS_SSL_PORT', '6380'))
        self.password = password or os.getenv('REDIS_KEY')
        self.use_ssl = use_ssl
        
        if not self.host:
            raise ValueError("Redis host is required (set REDIS_HOST env var)")
        
        # Create connection pool with SSL support
        pool_kwargs = {
            'host': self.host,
            'port': self.port,
            'password': self.password,
            'max_connections': max_connections,
            'connection_class': SSLConnection if use_ssl else redis.Connection,
            'socket_connect_timeout': connection_timeout,
            'socket_timeout': socket_timeout,
            'retry_on_timeout': retry_on_timeout,
            'health_check_interval': health_check_interval,
        }
        
        if use_ssl:
            pool_kwargs['ssl_cert_reqs'] = ssl_cert_reqs
            pool_kwargs['ssl_ca_certs'] = None  # Use system CA bundle
            
        self.pool = ConnectionPool(**pool_kwargs)
        self.client: Optional[Redis] = None
        self.stats = CacheStats()
        self._connected = False
        
        # Try to establish connection
        self._connect()
    
    def _connect(self) -> bool:
        """Establish connection to Redis"""
        try:
            self.client = Redis(connection_pool=self.pool)
            # Test connection
            self.client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.host}:{self.port} (SSL: {self.use_ssl})")
            return True
        except (RedisError, Exception) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False
    
    @classmethod
    def from_env(cls) -> Optional['RedisCache']:
        """Create RedisCache from environment variables"""
        try:
            return cls()
        except (ValueError, RedisError) as e:
            logger.warning(f"Redis cache not available: {e}")
            return None
    
    def is_connected(self) -> bool:
        """Check if Redis is connected and responsive"""
        if not self._connected or not self.client:
            return False
        
        try:
            self.client.ping()
            return True
        except (RedisError, Exception):
            self._connected = False
            return False
    
    def _generate_key(self, key: str, prefix: str = "", version: str = "v1") -> str:
        """Generate cache key with prefix and version"""
        parts = []
        if prefix:
            parts.append(prefix)
        if version:
            parts.append(version)
        parts.append(key)
        return ":".join(parts)
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value for storage"""
        if value is None:
            return b''
        return json.dumps(value, default=str).encode('utf-8')
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value from storage"""
        if not data:
            return None
        return json.loads(data.decode('utf-8'))
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache
        
        Args:
            key: Cache key
            default: Default value if key not found
            
        Returns:
            Cached value or default
        """
        if not self.is_connected():
            self.stats.errors += 1
            return default
        
        self.stats.total_requests += 1
        start_time = time.time()
        
        try:
            data = self.client.get(key)
            elapsed = time.time() - start_time
            
            if data is not None:
                self.stats.hits += 1
                self.stats.hit_time_sum += elapsed
                return self._deserialize(data)
            else:
                self.stats.misses += 1
                self.stats.miss_time_sum += elapsed
                return default
                
        except (RedisError, Exception) as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self.stats.errors += 1
            return default
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            return False
        
        try:
            serialized = self._serialize(value)
            
            kwargs = {}
            if ttl is not None:
                kwargs['ex'] = ttl
            if nx:
                kwargs['nx'] = True
            if xx:
                kwargs['xx'] = True
            
            result = self.client.set(key, serialized, **kwargs)
            return bool(result)
            
        except (RedisError, Exception) as e:
            logger.error(f"Cache set error for key {key}: {e}")
            self.stats.errors += 1
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.is_connected():
            return False
        
        try:
            result = self.client.delete(key)
            return bool(result)
        except (RedisError, Exception) as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern
        
        Args:
            pattern: Redis key pattern (e.g., "todoist:tasks:*")
            
        Returns:
            Number of keys deleted
        """
        if not self.is_connected():
            return 0
        
        try:
            # Use SCAN to avoid blocking on large keyspaces
            deleted = 0
            for key in self.client.scan_iter(match=pattern, count=100):
                if self.client.delete(key):
                    deleted += 1
            return deleted
            
        except (RedisError, Exception) as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.is_connected():
            return False
        
        try:
            return bool(self.client.exists(key))
        except (RedisError, Exception):
            return False
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for key"""
        if not self.is_connected():
            return False
        
        try:
            return bool(self.client.expire(key, ttl))
        except (RedisError, Exception):
            return False
    
    def ttl(self, key: str) -> int:
        """Get remaining TTL for key in seconds"""
        if not self.is_connected():
            return -2  # Key doesn't exist
        
        try:
            return self.client.ttl(key)
        except (RedisError, Exception):
            return -2
    
    def flush_all(self) -> bool:
        """Flush all keys (use with caution!)"""
        if not self.is_connected():
            return False
        
        try:
            self.client.flushall()
            return True
        except (RedisError, Exception) as e:
            logger.error(f"Cache flush error: {e}")
            return False
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        return self.stats
    
    def reset_stats(self):
        """Reset cache statistics"""
        self.stats.reset()
    
    def info(self) -> Dict[str, Any]:
        """Get Redis server info"""
        if not self.is_connected():
            return {}
        
        try:
            return self.client.info()
        except (RedisError, Exception):
            return {}
    
    def close(self):
        """Close Redis connection"""
        if self.client:
            self.client.close()
        if self.pool:
            self.pool.disconnect()
        self._connected = False


def cache_key_generator(
    prefix: str,
    version: str = "v1",
    *args,
    **kwargs
) -> str:
    """
    Generate cache key from function arguments
    
    Args:
        prefix: Key prefix (e.g., "todoist:tasks")
        version: Cache version
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Cache key string
    """
    # Build key components
    parts = [prefix, version]
    
    # Add positional arguments
    for arg in args:
        if arg is not None:
            parts.append(str(arg))
    
    # Add keyword arguments (sorted for consistency)
    if kwargs:
        # Filter out None values and create sorted param string
        params = {k: v for k, v in kwargs.items() if v is not None}
        if params:
            param_str = json.dumps(params, sort_keys=True, default=str)
            param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
            parts.append(param_hash)
    
    return ":".join(parts)


def cache_aside(
    config: Optional[CacheConfig] = None,
    cache_instance: Optional[RedisCache] = None,
    key_func: Optional[Callable] = None
):
    """
    Decorator for cache-aside pattern
    
    Args:
        config: Cache configuration
        cache_instance: Redis cache instance to use
        key_func: Custom key generation function
        
    Example:
        @cache_aside(CacheConfig(ttl=60, key_prefix="todoist:tasks"))
        def get_tasks(project_id: str):
            # Expensive API call
            return api.get_tasks(project_id)
    """
    if config is None:
        config = CacheConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Get cache instance
            cache = cache_instance
            if cache is None:
                # Try to get from first argument if it has a cache attribute
                if args and hasattr(args[0], 'cache'):
                    cache = args[0].cache
            
            # If no cache available, just call function
            if cache is None or not cache.is_connected():
                return func(*args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Skip 'self' argument for instance methods
                key_args = args[1:] if args and hasattr(args[0], '__class__') else args
                cache_key = cache_key_generator(
                    config.key_prefix or func.__name__,
                    config.version,
                    *key_args,
                    **kwargs
                )
            
            # Try to get from cache
            start_time = time.time()
            cached_value = cache.get(cache_key)
            
            if cached_value is not None:
                logger.debug(f"Cache hit for {cache_key} ({time.time() - start_time:.3f}s)")
                return cached_value
            
            # Cache miss - call function
            logger.debug(f"Cache miss for {cache_key}")
            result = func(*args, **kwargs)
            
            # Store in cache
            if result is not None:
                cache.set(cache_key, result, ttl=config.get_ttl_seconds())
            
            return result
        
        # Add cache management methods to wrapper
        wrapper.invalidate = lambda *args, **kwargs: _invalidate_cache(
            cache_instance, config, key_func, func, *args, **kwargs
        )
        
        return wrapper
    
    return decorator


def _invalidate_cache(
    cache_instance: Optional[RedisCache],
    config: CacheConfig,
    key_func: Optional[Callable],
    func: Callable,
    *args,
    **kwargs
) -> bool:
    """Invalidate cache for specific function call"""
    cache = cache_instance
    if cache is None:
        if args and hasattr(args[0], 'cache'):
            cache = args[0].cache
    
    if cache is None:
        return False
    
    if key_func:
        cache_key = key_func(*args, **kwargs)
    else:
        key_args = args[1:] if args and hasattr(args[0], '__class__') else args
        cache_key = cache_key_generator(
            config.key_prefix or func.__name__,
            config.version,
            *key_args,
            **kwargs
        )
    
    return cache.delete(cache_key)


def _get_cache_ttl(env_var: str, default: int) -> int:
    """Get TTL value from environment or use default"""
    env_value = os.getenv(f"CACHE_TTL_{env_var}")
    if env_value:
        try:
            value = int(env_value)
            if value < 0:
                logger.warning(f"Invalid negative TTL for CACHE_TTL_{env_var}: {value}, using default: {default}")
                return default
            logger.debug(f"Using custom TTL for {env_var}: {value} seconds (default was {default})")
            return value
        except ValueError:
            logger.warning(f"Invalid TTL value for CACHE_TTL_{env_var}: {env_value}, using default: {default}")
    return default


# TTL constants for different data types (in seconds)
class CacheTTL:
    """
    Standard TTL values for different data types.
    
    All values can be overridden via environment variables by prefixing with CACHE_TTL_
    For example: CACHE_TTL_HA_STATES=5 will set HA_STATES to 5 seconds
    
    Environment Variables:
        CACHE_TTL_TODOIST_TASKS: Task list cache (default: 60 seconds)
        CACHE_TTL_TODOIST_PROJECTS: Project list cache (default: 300 seconds)
        CACHE_TTL_TODOIST_LABELS: Label list cache (default: 600 seconds)
        CACHE_TTL_TODOIST_SECTIONS: Section list cache (default: 300 seconds)
        CACHE_TTL_TODOIST_COMMENTS: Comment cache (default: 120 seconds)
        
        CACHE_TTL_HA_STATES: Entity states cache (default: 3 seconds)
        CACHE_TTL_HA_SINGLE_STATE: Single entity state (default: 2 seconds)
        CACHE_TTL_HA_DEVICE_LIST: Device metadata cache (default: 1800 seconds)
        CACHE_TTL_HA_ENTITY_LIST: Entity metadata cache (default: 1800 seconds)
        CACHE_TTL_HA_AREAS: Area list cache (default: 3600 seconds)
        CACHE_TTL_HA_SERVICES: Service list cache (default: 3600 seconds)
        CACHE_TTL_HA_HISTORY: History data cache (default: 300 seconds)
        
        CACHE_TTL_CALENDAR_EVENTS: Calendar events cache (default: 900 seconds)
        CACHE_TTL_CALENDAR_INFO: Calendar info cache (default: 1800 seconds)
        CACHE_TTL_CALENDAR_FEED: Calendar feed cache (default: 600 seconds)
    """
    
    # Todoist
    TODOIST_TASKS = _get_cache_ttl("TODOIST_TASKS", 60)  # 1 minute default
    TODOIST_PROJECTS = _get_cache_ttl("TODOIST_PROJECTS", 300)  # 5 minutes default
    TODOIST_LABELS = _get_cache_ttl("TODOIST_LABELS", 600)  # 10 minutes default
    TODOIST_SECTIONS = _get_cache_ttl("TODOIST_SECTIONS", 300)  # 5 minutes default
    TODOIST_COMMENTS = _get_cache_ttl("TODOIST_COMMENTS", 120)  # 2 minutes default
    
    # Home Assistant
    HA_STATES = _get_cache_ttl("HA_STATES", 3)  # 3 seconds default (real-time critical)
    HA_SINGLE_STATE = _get_cache_ttl("HA_SINGLE_STATE", 2)  # 2 seconds default
    HA_DEVICE_LIST = _get_cache_ttl("HA_DEVICE_LIST", 1800)  # 30 minutes default
    HA_ENTITY_LIST = _get_cache_ttl("HA_ENTITY_LIST", 1800)  # 30 minutes default
    HA_AREAS = _get_cache_ttl("HA_AREAS", 3600)  # 1 hour default
    HA_SERVICES = _get_cache_ttl("HA_SERVICES", 3600)  # 1 hour default
    HA_HISTORY = _get_cache_ttl("HA_HISTORY", 300)  # 5 minutes default
    
    # Calendar
    CALENDAR_EVENTS = _get_cache_ttl("CALENDAR_EVENTS", 900)  # 15 minutes default
    CALENDAR_INFO = _get_cache_ttl("CALENDAR_INFO", 1800)  # 30 minutes default
    CALENDAR_FEED = _get_cache_ttl("CALENDAR_FEED", 600)  # 10 minutes default