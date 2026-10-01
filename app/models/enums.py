import enum


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    OPS_MANAGER = "ops_manager"
    SUPPORT_AGENT = "support_agent"
    NETWORK_ENGINEER = "network_engineer"
    FIELD_TECHNICIAN = "field_technician"
    CUSTOMER = "customer"


STAFF_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.OPS_MANAGER,
    UserRole.SUPPORT_AGENT,
    UserRole.NETWORK_ENGINEER,
    UserRole.FIELD_TECHNICIAN,
}


class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class PlanType(str, enum.Enum):
    PREPAID = "prepaid"
    POSTPAID = "postpaid"


class PlanCategory(str, enum.Enum):
    DATA = "data"
    VOICE = "voice"
    SMS = "sms"
    COMBO = "combo"


class PlanStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SimType(str, enum.Enum):
    PHYSICAL = "physical"
    ESIM = "esim"


class SimStatus(str, enum.Enum):
    AVAILABLE = "available"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOST = "lost"
    BLOCKED = "blocked"
    DEACTIVATED = "deactivated"


class DeviceType(str, enum.Enum):
    SMARTPHONE = "smartphone"
    ROUTER = "router"
    IOT = "iot"
    TABLET = "tablet"
    OTHER = "other"


class DeviceStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TowerType(str, enum.Enum):
    MACRO = "macro"
    MICRO = "micro"
    PICO = "pico"
    FEMTO = "femto"


class TowerStatus(str, enum.Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"
    DECOMMISSIONED = "decommissioned"


class EquipmentType(str, enum.Enum):
    ROUTER = "router"
    SWITCH = "switch"
    BASE_STATION = "base_station"
    OTHER = "other"


class EquipmentStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class OutageType(str, enum.Enum):
    PLANNED = "planned"
    UNPLANNED = "unplanned"


class OutageSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OutageStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class TechnicianAvailability(str, enum.Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFF_DUTY = "off_duty"


class AssignmentTargetType(str, enum.Enum):
    TICKET = "ticket"
    OUTAGE = "outage"


class AssignmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TicketCategory(str, enum.Enum):
    NETWORK_ISSUE = "network_issue"
    SIM_ISSUE = "sim_issue"
    DATA_ISSUE = "data_issue"
    VOICE_ISSUE = "voice_issue"
    DEVICE_ISSUE = "device_issue"
    ACCOUNT_ISSUE = "account_issue"
    SERVICE_REQUEST = "service_request"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CustomerType(str, enum.Enum):
    PREPAID = "prepaid"
    POSTPAID = "postpaid"
    ENTERPRISE = "enterprise"


class ServiceRequestType(str, enum.Enum):
    SIM_REPLACEMENT = "sim_replacement"
    NUMBER_CHANGE = "number_change"
    PLAN_CHANGE = "plan_change"
    DEVICE_REPLACEMENT = "device_replacement"
    SERVICE_ACTIVATION = "service_activation"
    SERVICE_SUSPENSION = "service_suspension"
    SERVICE_TERMINATION = "service_termination"


class ServiceRequestStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class NotificationType(str, enum.Enum):
    TICKET_ASSIGNMENT = "ticket_assignment"
    SLA_BREACH = "sla_breach"
    NETWORK_OUTAGE = "network_outage"
    SERVICE_RESTORATION = "service_restoration"
    PLAN_EXPIRY = "plan_expiry"
    USAGE_THRESHOLD = "usage_threshold"
    SIM_SUSPENSION = "sim_suspension"
    MAINTENANCE_SCHEDULE = "maintenance_schedule"
