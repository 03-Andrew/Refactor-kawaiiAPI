# terraform {
#   required_version = ">=1.10.0"
#   backend "s3" {
#     bucket = "booking-terraform-s3-bucket"
#     key = "booking/terraform.tfstate"
#     region  = "ap-southeast-1"
#     encrypt = true
#   }
# }