import structlog
import logging

def mask_sensitive_keys(logger, log_method, event_dict):
    """Custom structlog processor to mask sensitive keys in logs."""
    sensitive_substrings = {"token", "password", "api_key", "key", "authorization", "auth", "secret"}
    for k in list(event_dict.keys()):
        if any(sub in k.lower() for sub in sensitive_substrings):
            event_dict[k] = "********"
    return event_dict

def setup_logging():
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            mask_sensitive_keys,
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

def get_logger(name: str):
    return structlog.get_logger(name)
