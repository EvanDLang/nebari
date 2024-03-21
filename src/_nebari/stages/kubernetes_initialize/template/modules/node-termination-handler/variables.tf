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

#variable "name" {
#  description = "Prefix name to assign to nebari resources"
#  type        = string
#}