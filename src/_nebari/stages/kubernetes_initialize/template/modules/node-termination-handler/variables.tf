variable "sqs_name" {
  description = "sqs_queue_name"
  type        = string
  default = "sqs_spot_queue"
}

variable "aws_region" {
  description = "AWS Region that cluster autoscaler is running"
  type        = string
}

variable "cluster_name" {
  description = "Cluster name for kubernetes cluster"
  type        = string
}

variable "namespace" {
  description = "Namespace to create Kubernetes resources"
  type        = string
}

variable "overrides" {
  description = "Jupyterhub helm chart list of overrides"
  type        = list(string)
  default     = []
}
