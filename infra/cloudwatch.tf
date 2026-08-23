variable "log_names" {
    type = list(string)
    default = [ "booking-api-logs", "celery-logs", "redis-logs", "nginx-logs" ]
}

resource "aws_cloudwatch_log_group" "booking-logs" {
    name = "booking-logs"
    log_group_class = "STANDARD"
}

resource "aws_cloudwatch_log_stream" "booking-backend" {
    for_each = toset(var.log_names)
    name = each.value
    log_group_name =  aws_cloudwatch_log_group.booking-logs.name
}


