variable "project_id" {
  description = "GCP project that hosts the whole S1 stack."
  type        = string
}

variable "region" {
  description = "Region for the state bucket (same as every other stack)."
  type        = string
  default     = "us-central1"
}

variable "billing_account_id" {
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX). Empty = skip the budget alerts."
  type        = string
  default     = ""
}

variable "budget_amount" {
  description = "Budget size, in the billing account's currency."
  type        = number
  default     = 50
}

variable "budget_currency" {
  description = "Must match the billing account's currency (check Billing > Account management)."
  type        = string
  default     = "USD"
}
