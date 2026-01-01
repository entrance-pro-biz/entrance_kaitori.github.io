provider "aws" {
  region = "ap-northeast-1"
}

# --- 1. S3 Bucket (Webサイト用) ---
resource "aws_s3_bucket" "gallery_bucket" {
  bucket = "entrance-pro-biz-kaitori"
}

resource "aws_s3_bucket_website_configuration" "gallery_site" {
  bucket = aws_s3_bucket.gallery_bucket.id
  index_document {
    suffix = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "gallery_bucket_block" {
  bucket = aws_s3_bucket.gallery_bucket.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "public_read" {
  bucket = aws_s3_bucket.gallery_bucket.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadGetObject"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.gallery_bucket.arn}/*"
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.gallery_bucket_block]
}

# --- 2. IAM Role & Policy (Lambda用) ---
resource "aws_iam_role" "lambda_exec_role" {
  name = "gallery_lambda_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "lambda_s3_policy" {
  name = "gallery_lambda_s3_policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject"]
        Resource = [aws_s3_bucket.gallery_bucket.arn, "${aws_s3_bucket.gallery_bucket.arn}/*"]
      },
      {
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_s3_policy.arn
}

# --- 3. Lambda Function ---
data "archive_file" "dummy" {
  type        = "zip"
  output_path = "dummy.zip"
  source {
    content  = "def lambda_handler(e, c): print('init')"
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "gallery_sync" {
  filename      = "dummy.zip"
  function_name = "card_gallery_sync"
  role          = aws_iam_role.lambda_exec_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300
  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.gallery_bucket.id
      GOOGLE_API_KEY = "dummy"
      SPREADSHEET_ID = "dummy"
    }
  }
}
