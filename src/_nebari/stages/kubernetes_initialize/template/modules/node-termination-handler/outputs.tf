output "sqs_queue_arn" {
  value = aws_sqs_queue.spot_queue.arn
}

output "iam_role_arn" {
  value = aws_iam_role.asg_sqs_role.arn
}

output "sa_policy_arn" {
  value = aws_iam_policy.node_termination_handler_sa_policy.arn
}

output "sqs_url" {
  value = aws_sqs_queue.spot_queue.url
}