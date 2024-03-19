output "credentials" {
  description = "Important credentials for connecting to S3 bucket"
  value = {
    bucket             = aws_s3_bucket.main.bucket
    bucket_domain_name = aws_s3_bucket.main.bucket_domain_name
    arn                = aws_s3_bucket.main.arn
  }
}

output "aws_iam_s3_policy_arn" {
  value  = aws_iam_policy.s3_access_policy.arn
}