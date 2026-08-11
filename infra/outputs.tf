output "PublicIP" {
    value = aws_instance.booking-ec2-instance.public_ip
}

output "RDSHost" {
    value = aws_db_instance.booking.address
}

output "RDSPort" {
    value = aws_db_instance.booking.port
}

output "DATABASE_URL" {
    value = "postgres://${aws_db_instance.booking.username}:${aws_db_instance.booking.password}@${aws_db_instance.booking.address}:${aws_db_instance.booking.port}/${aws_db_instance.booking.db_name}"
    sensitive = true
}

output "ELASTIC_IP" {
    value = aws_eip.booking-eip.public_ip
}