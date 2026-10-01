# API Reference

117 endpoints. Interactive docs: `/docs` (Swagger UI) and `/redoc`. Endpoints marked 🔒 need a Bearer token.


## Advanced Reports

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/reports/customer-growth` | Customer Growth | 🔒 |
| `GET` | `/api/v1/reports/customer-service-trends` | Customer Service Trends | 🔒 |
| `GET` | `/api/v1/reports/data-consumption` | Data Consumption | 🔒 |
| `GET` | `/api/v1/reports/network-uptime` | Network Uptime | 🔒 |
| `GET` | `/api/v1/reports/outage-frequency` | Outage Frequency | 🔒 |
| `GET` | `/api/v1/reports/plan-popularity` | Plan Popularity | 🔒 |
| `GET` | `/api/v1/reports/sla-performance` | Sla Performance | 🔒 |
| `GET` | `/api/v1/reports/subscription-trends` | Subscription Trends | 🔒 |
| `GET` | `/api/v1/reports/technician-performance` | Technician Performance | 🔒 |
| `GET` | `/api/v1/reports/ticket-resolution-time` | Ticket Resolution Time | 🔒 |

## Audit Logs

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/audit-logs` | List Audit Logs | 🔒 |

## Authentication

| Method | Path | Summary | Auth |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Login | public |
| `POST` | `/api/v1/auth/logout` | Logout | public |
| `GET` | `/api/v1/auth/me` | Me | 🔒 |
| `POST` | `/api/v1/auth/password-change` | Change Password | 🔒 |
| `POST` | `/api/v1/auth/password-reset/confirm` | Confirm Password Reset | public |
| `POST` | `/api/v1/auth/password-reset/request` | Request Password Reset | public |
| `POST` | `/api/v1/auth/refresh` | Refresh | public |
| `POST` | `/api/v1/auth/register` | Register | public |
| `POST` | `/api/v1/auth/users` | Admin Create User | 🔒 |
| `PATCH` | `/api/v1/auth/users/{user_id}/activation` | Set User Activation | 🔒 |

## Customers

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/customers` | List Customers | 🔒 |
| `POST` | `/api/v1/customers` | Create Customer | 🔒 |
| `DELETE` | `/api/v1/customers/{customer_id}` | Delete Customer | 🔒 |
| `GET` | `/api/v1/customers/{customer_id}` | Get Customer | 🔒 |
| `PATCH` | `/api/v1/customers/{customer_id}` | Update Customer | 🔒 |
| `PATCH` | `/api/v1/customers/{customer_id}/activation` | Set Activation | 🔒 |
| `POST` | `/api/v1/customers/{customer_id}/addresses` | Add Address | 🔒 |
| `GET` | `/api/v1/customers/{customer_id}/history` | Customer History | 🔒 |
| `PATCH` | `/api/v1/customers/{customer_id}/kyc` | Update Kyc | 🔒 |

## Devices

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/devices` | List Devices | 🔒 |
| `POST` | `/api/v1/devices` | Create Device | 🔒 |
| `GET` | `/api/v1/devices/{device_id}` | Get Device | 🔒 |
| `PATCH` | `/api/v1/devices/{device_id}` | Update Device | 🔒 |
| `POST` | `/api/v1/devices/{device_id}/assign-sim` | Assign Sim | 🔒 |

## Field Technicians

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/technicians` | List Technicians | 🔒 |
| `POST` | `/api/v1/technicians` | Create Technician | 🔒 |
| `POST` | `/api/v1/technicians/assignments` | Assign Technician | 🔒 |
| `POST` | `/api/v1/technicians/assignments/{assignment_id}/complete` | Complete Assignment | 🔒 |
| `POST` | `/api/v1/technicians/assignments/{assignment_id}/reassign` | Reassign | 🔒 |
| `GET` | `/api/v1/technicians/{technician_id}` | Get Technician | 🔒 |
| `PATCH` | `/api/v1/technicians/{technician_id}` | Update Technician | 🔒 |
| `GET` | `/api/v1/technicians/{technician_id}/assignments` | Assignments | 🔒 |
| `GET` | `/api/v1/technicians/{technician_id}/workload` | Workload | 🔒 |

## Health

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/health` | Health | public |

## Network Equipment

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/equipment` | List Equipment | 🔒 |
| `POST` | `/api/v1/equipment` | Create Equipment | 🔒 |
| `GET` | `/api/v1/equipment/stale` | Stale Equipment | 🔒 |
| `GET` | `/api/v1/equipment/{equipment_id}` | Get Equipment | 🔒 |
| `POST` | `/api/v1/equipment/{equipment_id}/heartbeat` | Heartbeat | 🔒 |

## Network Outages

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/outages` | List Outages | 🔒 |
| `POST` | `/api/v1/outages` | Create Outage | 🔒 |
| `GET` | `/api/v1/outages/{outage_id}` | Get Outage | 🔒 |
| `GET` | `/api/v1/outages/{outage_id}/affected-customers` | Affected Customers | 🔒 |
| `POST` | `/api/v1/outages/{outage_id}/in-progress` | Mark In Progress | 🔒 |
| `POST` | `/api/v1/outages/{outage_id}/resolve` | Resolve Outage | 🔒 |

## Network Towers

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/towers` | List Towers | 🔒 |
| `POST` | `/api/v1/towers` | Create Tower | 🔒 |
| `GET` | `/api/v1/towers/{tower_id}` | Get Tower | 🔒 |
| `PATCH` | `/api/v1/towers/{tower_id}` | Update Tower | 🔒 |
| `PATCH` | `/api/v1/towers/{tower_id}/status` | Set Tower Status | 🔒 |

## Notifications

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/notifications` | My Notifications | 🔒 |
| `GET` | `/api/v1/notifications/all` | All Notifications | 🔒 |
| `PATCH` | `/api/v1/notifications/{notification_id}/read` | Mark Read | 🔒 |

## Operations Dashboard

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/dashboard/operations` | Operations Dashboard | 🔒 |

## Operations Jobs

| Method | Path | Summary | Auth |
|---|---|---|---|
| `POST` | `/api/v1/ops/run-jobs` | Run Scheduled Jobs | 🔒 |

## SIM Cards

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/sims` | List Sims | 🔒 |
| `POST` | `/api/v1/sims` | Create Sim | 🔒 |
| `GET` | `/api/v1/sims/customers/{customer_id}/replacements` | Replacement History | 🔒 |
| `GET` | `/api/v1/sims/{sim_id}` | Get Sim | 🔒 |
| `POST` | `/api/v1/sims/{sim_id}/assign-customer` | Assign Customer | 🔒 |
| `POST` | `/api/v1/sims/{sim_id}/assign-plan` | Assign Plan | 🔒 |
| `POST` | `/api/v1/sims/{sim_id}/assign-tower` | Assign Tower | 🔒 |
| `POST` | `/api/v1/sims/{sim_id}/replace` | Replace Sim | 🔒 |
| `PATCH` | `/api/v1/sims/{sim_id}/status` | Change Status | 🔒 |

## SLA Management

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/sla/breached` | Breached | 🔒 |
| `GET` | `/api/v1/sla/rules` | List Rules | 🔒 |
| `POST` | `/api/v1/sla/rules` | Create Rule | 🔒 |
| `GET` | `/api/v1/sla/soon-to-breach` | Soon To Breach | 🔒 |
| `GET` | `/api/v1/sla/tickets/{ticket_id}` | Ticket Sla | 🔒 |
| `POST` | `/api/v1/sla/tickets/{ticket_id}/escalate` | Escalate | 🔒 |

## Service Plans

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/plans` | List Plans | public |
| `POST` | `/api/v1/plans` | Create Plan | 🔒 |
| `POST` | `/api/v1/plans/compare` | Compare Plans | public |
| `GET` | `/api/v1/plans/{plan_id}` | Get Plan | public |
| `PATCH` | `/api/v1/plans/{plan_id}` | Update Plan | 🔒 |
| `PATCH` | `/api/v1/plans/{plan_id}/status` | Set Plan Status | 🔒 |

## Service Requests

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/service-requests` | List Requests | 🔒 |
| `POST` | `/api/v1/service-requests` | Create Request | 🔒 |
| `GET` | `/api/v1/service-requests/{request_id}` | Get Request | 🔒 |
| `GET` | `/api/v1/service-requests/{request_id}/history` | Get History | 🔒 |
| `PATCH` | `/api/v1/service-requests/{request_id}/status` | Update Status | 🔒 |

## Subscriptions

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/subscriptions` | List Subscriptions | 🔒 |
| `POST` | `/api/v1/subscriptions` | Create Subscription | 🔒 |
| `GET` | `/api/v1/subscriptions/{subscription_id}` | Get Subscription | 🔒 |
| `POST` | `/api/v1/subscriptions/{subscription_id}/cancel` | Cancel | 🔒 |
| `POST` | `/api/v1/subscriptions/{subscription_id}/change-plan` | Change Plan | 🔒 |
| `GET` | `/api/v1/subscriptions/{subscription_id}/history` | History | 🔒 |
| `POST` | `/api/v1/subscriptions/{subscription_id}/reactivate` | Reactivate | 🔒 |
| `POST` | `/api/v1/subscriptions/{subscription_id}/renew` | Renew | 🔒 |
| `POST` | `/api/v1/subscriptions/{subscription_id}/suspend` | Suspend | 🔒 |

## Support Tickets

| Method | Path | Summary | Auth |
|---|---|---|---|
| `GET` | `/api/v1/tickets` | List Tickets | 🔒 |
| `POST` | `/api/v1/tickets` | Create Ticket | 🔒 |
| `GET` | `/api/v1/tickets/{ticket_id}` | Get Ticket | 🔒 |
| `POST` | `/api/v1/tickets/{ticket_id}/assign-agent` | Assign Agent | 🔒 |
| `POST` | `/api/v1/tickets/{ticket_id}/assign-technician` | Assign Technician | 🔒 |
| `GET` | `/api/v1/tickets/{ticket_id}/comments` | Get Comments | 🔒 |
| `POST` | `/api/v1/tickets/{ticket_id}/comments` | Add Comment | 🔒 |
| `POST` | `/api/v1/tickets/{ticket_id}/escalate` | Escalate | 🔒 |
| `GET` | `/api/v1/tickets/{ticket_id}/history` | Get History | 🔒 |
| `PATCH` | `/api/v1/tickets/{ticket_id}/priority` | Set Priority | 🔒 |
| `PATCH` | `/api/v1/tickets/{ticket_id}/status` | Update Status | 🔒 |

## Usage Tracking

| Method | Path | Summary | Auth |
|---|---|---|---|
| `POST` | `/api/v1/usage` | Record Usage | 🔒 |
| `GET` | `/api/v1/usage/customers/{customer_id}` | Customer Usage | 🔒 |
| `GET` | `/api/v1/usage/plans/{plan_id}/utilization` | Plan Utilization | 🔒 |
| `GET` | `/api/v1/usage/sims/{sim_id}` | Sim Usage | 🔒 |
| `GET` | `/api/v1/usage/subscriptions/{subscription_id}/summary` | Subscription Summary | 🔒 |
