data "aws_iam_role" "node-group" {
  name = "${var.cluster_name}-eks-node-group-role"
}

resource "aws_s3_bucket" "main" {
  bucket = "${var.cluster_name}-user-bucket"
  acl    = var.public ? "public-read" : "private"

  versioning {
    enabled = true
  }

  tags = merge({
    Name        = "${var.cluster_name}-user-bucket"
    Description = "S3 bucket for ${var.cluster_name}-user-bucket"
  }, var.tags)
}

# Attach policies to the IAM role allowing access to the S3 bucket
resource "aws_iam_policy" "s3_access_policy" {
  name        = "${var.cluster_name}-s3_access_policy"
  description = "IAM policy for S3 bucket access"

  policy = jsonencode(
    {
          "Version": "2012-10-17",
          "Statement": [
              {
                  "Sid": "BioSCapeUserBucket",
                  "Effect": "Allow",
                  "Action": [
                      "s3:ListBucket",
                      "s3:DeleteObject",
                      "s3:DeleteObjectVersion",
                      "s3:GetObject",
                      "s3:GetObjectAttributes",
                      "s3:PutObject",
                      "s3:GetObjectVersion",
                      "s3:AbortMultipartUpload",
                      "s3:RestoreObject",
                      "s3:ReplicateObject"
                  ],
                  "Resource": [
                    aws_s3_bucket.main.arn,
                    "${aws_s3_bucket.main.arn}/*"
                  ]
              },
              {
                  "Sid": "BioSCapeDataBucket",
                  "Effect": "Allow",
                  "Action": [
                      "s3:ListBucket",
                      "s3:GetObject",
                      "s3:GetObjectAttributes",
                      "s3:GetObjectVersion"
                  ],
                  "Resource": [
                      "arn:aws:s3:::bioscape-data",
                      "arn:aws:s3:::bioscape-data/*"
                  ]
              }
          ]
      }

  )
}

resource "aws_iam_role_policy_attachment" "s3_policy_attachment" {
  policy_arn = aws_iam_policy.s3_access_policy.arn
  role       = data.aws_iam_role.node-group.name
}