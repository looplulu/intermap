"""Navigation Session state definitions."""

from enum import Enum


class SessionStatus(str, Enum):
    """Navigation Session lifecycle states."""
    IDLE = "idle"
    ACTIVE = "active"
    NAVIGATING = "navigating"
    COMPLETE = "complete"
    ERROR = "error"


class TaskType(str, Enum):
    """Supported task types."""
    REFUND = "refund"
    CONTACT_CUSTOMER_SERVICE = "contact_customer_service"
    FIND_ORDER = "find_order"


class AppType(str, Enum):
    """Supported apps."""
    TAOBAO = "taobao"
    JD = "jd"
    PDD = "pdd"


# Mapping: task keyword -> TaskType
TASK_KEYWORDS = {
    # Chinese
    "退款": TaskType.REFUND,
    "退货": TaskType.REFUND,
    "售后": TaskType.REFUND,
    "客服": TaskType.CONTACT_CUSTOMER_SERVICE,
    "联系客服": TaskType.CONTACT_CUSTOMER_SERVICE,
    "订单": TaskType.FIND_ORDER,
    "查订单": TaskType.FIND_ORDER,
    "找订单": TaskType.FIND_ORDER,
    "我的订单": TaskType.FIND_ORDER,
    # English
    "refund": TaskType.REFUND,
    "return": TaskType.REFUND,
    "customer service": TaskType.CONTACT_CUSTOMER_SERVICE,
    "find order": TaskType.FIND_ORDER,
    "order": TaskType.FIND_ORDER,
}


def recognize_task(text: str) -> TaskType | None:
    """Recognize task type from user input text."""
    for keyword, task_type in TASK_KEYWORDS.items():
        if keyword in text:
            return task_type
    return None
