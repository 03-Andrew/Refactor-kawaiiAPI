resource "aws_iam_role" "cloudwatch-role" {
    name = "cloudwatch-role"

    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [{
            Action = "sts:AssumeRole"
            Effect = "Allow"
            Principal = {
                Service = "ec2.amazonaws.com"
            }
        }]
    })
}

data "aws_iam_policy" "cloudwatch_access" {
    arn = "arn:aws:iam::aws:policy/CloudWatchFullAccessV2"
}

resource "aws_iam_role_policy_attachment" "attach-roles" {
    role = aws_iam_role.cloudwatch-role.name
    policy_arn = data.aws_iam_policy.cloudwatch_access.arn
}

resource "aws_iam_instance_profile" "ec2-profile" {
    name = "ec2-role"
    role = aws_iam_role.cloudwatch-role.name
}