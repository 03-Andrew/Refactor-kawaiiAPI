resource "aws_db_subnet_group" "default" {
    name = "main"
    subnet_ids = [ aws_subnet.private_booking_subnet_1.id, aws_subnet.private_booking_subnet_2.id ]
    tags = {
        Name = "My db subnet group"
    }
}

resource "aws_security_group" "allow_postgres_traffic" {
  name = "allow_postgres"
  description = "Allow postgres traffic"
  vpc_id = aws_vpc.booking_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "allow_postgres" {
    security_group_id = aws_security_group.allow_postgres_traffic.id
    referenced_security_group_id = aws_security_group.terraform_sg.id
    from_port = 5432
    to_port = 5432
    ip_protocol = "tcp"
}


resource "aws_db_instance" "booking" {
  identifier = "booking-db"

  engine         = "postgres"
  engine_version = "16"

  instance_class = "db.t4g.micro"
  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = "booking"
  username = "postgres"
  password = var.PASSWORD

  db_subnet_group_name   = aws_db_subnet_group.default.name
  vpc_security_group_ids = [aws_security_group.allow_postgres_traffic.id]

  publicly_accessible = false

  backup_retention_period = 7

  skip_final_snapshot = true
}
