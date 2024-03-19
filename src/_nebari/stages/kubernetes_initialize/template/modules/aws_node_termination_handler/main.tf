data "aws_caller_identity" "current" {}

data "aws_iam_role" "node-group" {
  name = "${var.cluster_name}-eks-node-group-role"
}

data "aws_eks_node_group" "user" {
  cluster_name    = var.cluster_name
  node_group_name = "user"
}

resource "aws_sqs_queue" "spot_queue" {
  name = var.sqs_name
  sqs_managed_sse_enabled = true
  message_retention_seconds = 300
  
  policy = jsonencode(
    {
        "Version": "2012-10-17",
        "Id": "MyQueuePolicy",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": ["events.amazonaws.com", "sqs.amazonaws.com"]
            },
            "Action": "sqs:SendMessage",
            "Resource": [
                "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.sqs_name}"
            ]
        }]
    }
  )
}

resource "aws_iam_policy" "node_termination_handler_sa_policy" {
  name        = "node-termination-handler-sa-policy"

  policy = jsonencode(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "autoscaling:CompleteLifecycleAction",
                        "autoscaling:DescribeAutoScalingInstances",
                        "autoscaling:DescribeTags",
                        "ec2:DescribeInstances",
                        "sqs:DeleteMessage",
                        "sqs:ReceiveMessage"
                    ],
                    "Resource": "*"
                }
            ]
        }
    )
}

resource "aws_iam_role_policy_attachment" "node_termination_handler_sa_policy_attach" {
  policy_arn = aws_iam_policy.node_termination_handler_sa_policy.arn
  role       = data.aws_iam_role.node-group.name
}


resource "aws_iam_role" "asg_sqs_role" {
  name = "asg_sqs_role"

  assume_role_policy = jsonencode(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "sts:AssumeRole"
                ],
                "Principal": {
                    "Service": [
                        "autoscaling.amazonaws.com"
                    ]
                }
            }
        ]
    }
  )

  managed_policy_arns = ["arn:aws:iam::aws:policy/service-role/AutoScalingNotificationAccessRole"]
}


resource "aws_autoscaling_lifecycle_hook" "spot_queue_life_cycle_hook_termination_user" {
  name                    = "spot_queue_life_cycle_hook_termination_user"
  autoscaling_group_name  = data.aws_eks_node_group.user.resources[0].autoscaling_groups[0].name
  default_result          = "CONTINUE"
  heartbeat_timeout       = 300
  lifecycle_transition    = "autoscaling:EC2_INSTANCE_TERMINATING"
  notification_target_arn = aws_sqs_queue.spot_queue.arn
  role_arn                = aws_iam_role.asg_sqs_role.arn

  depends_on = [
    data.aws_eks_node_group.user
  ]
}

resource "aws_autoscaling_group_tag" "lifecycle_hook_user" {
  autoscaling_group_name = data.aws_eks_node_group.user.resources[0].autoscaling_groups[0].name
  tag {
    key                 = "aws-node-termination-handler/managed"
    value               = "true"
    propagate_at_launch = true
  }
  depends_on = [
    data.aws_eks_node_group.user
  ]
}

data "aws_eks_node_group" "worker" {
  cluster_name    = var.cluster_name
  node_group_name = "worker"
}

resource "aws_autoscaling_lifecycle_hook" "spot_queue_life_cycle_hook_termination_worker" {   
  name                    = "spot_queue_life_cycle_hook_termination_worker"
  autoscaling_group_name  = data.aws_eks_node_group.worker.resources[0].autoscaling_groups[0].name
  default_result          = "CONTINUE"
  heartbeat_timeout       = 300
  lifecycle_transition    = "autoscaling:EC2_INSTANCE_TERMINATING"
  notification_target_arn = aws_sqs_queue.spot_queue.arn
  role_arn                = aws_iam_role.asg_sqs_role.arn
  
  depends_on = [
    data.aws_eks_node_group.worker
  ]
}

resource "aws_autoscaling_group_tag" "lifecycle_hook_worker" {
  autoscaling_group_name = data.aws_eks_node_group.worker.resources[0].autoscaling_groups[0].name
  tag {
    key                 = "aws-node-termination-handler/managed"
    value               = "true"
    propagate_at_launch = true
  }
  depends_on = [
    data.aws_eks_node_group.worker
  ]
}

resource "helm_release" "node_termination_handler_release" {
  count      = 1
  chart      = "aws-node-termination-handler"
  namespace  = var.namespace
  name       = "aws-node-termination-handler"
  #version    = "0.12.0"
  repository = "https://aws.github.io/eks-charts"

  set {
    name = "enableSqsTerminationDraining"
    value = "true"
  } 

  set {
    name = "queueURL"
    value = aws_sqs_queue.spot_queue.url
  }

  set {
    name = "awsRegion"
    value = var.aws_region
  }

  depends_on = [
    aws_sqs_queue.spot_queue
  ]
}








#resource "aws_autoscaling_lifecycle_hook" "spot_queue_life_cycle_hook_launch_user" {
#  name                    = "spot_queue_life_cycle_hook_launch_user"
#  autoscaling_group_name  = data.aws_eks_node_group.user.resources[0].autoscaling_groups[0].name
#  default_result          = "ABANDON"
#  heartbeat_timeout       = 300
#  lifecycle_transition    = "autoscaling:EC2_INSTANCE_LAUNCHING"
#  notification_target_arn = aws_sqs_queue.spot_queue.arn
#  #role_arn                = aws_iam_role.cluster.arn
#
#  depends_on = [
#    data.aws_eks_node_group.user
#  ]
#}


#resource "aws_autoscaling_lifecycle_hook" "spot_queue_life_cycle_hook_launch_worker" {   
#  name                    = "spot_queue_life_cycle_hook_launch_worker"
#  autoscaling_group_name  = data.aws_eks_node_group.worker.resources[0].autoscaling_groups[0].name
#  default_result          = "ABANDON"
#  heartbeat_timeout       = 300
#  lifecycle_transition    = "autoscaling:EC2_INSTANCE_LAUNCHING"
#  notification_target_arn = aws_sqs_queue.spot_queue.arn
#  #role_arn                = aws_iam_role.cluster.arn
#  
#  depends_on = [
#    data.aws_eks_node_group.worker
#  ]
#}




#  set {
#    name = "nodeSelector"
#    value = "eks.amazonaws.com/nodegroup=general"
#  }

#resource "kubernetes_service_account" "node_termination_handler_sa" {
#  metadata {
#    name = "node-termination-handler-sa"
#    namespace = var.namespace
#    annotations = {
#         "eks.amazonaws.com/role-arn": aws_iam_policy.node_termination_handler_sa_policy.arn
#    }
#  }
#}