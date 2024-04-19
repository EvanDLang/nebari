data "aws_iam_role" "node-group" {
  name = "${var.cluster_name}-eks-node-group-role"
}

data "aws_iam_policy" "s3_access_policy" {
  name = "${var.cluster_name}-s3_access_policy"
}

resource "aws_iam_role_policy_attachment" "s3_policy_attachment" {
  policy_arn = data.aws_iam_policy.s3_access_policy.arn
  role       = data.aws_iam_role.node-group.name
}