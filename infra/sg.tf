resource "aws_security_group" "terraform_sg" {
    name = "booking-terraform-sg"
    description = "sg to allow ssh and http traffic"
    vpc_id = aws_vpc.booking_vpc.id
    tags = {
        Name = "Terraform_proj_sg"
    }
}

resource "aws_vpc_security_group_ingress_rule" "allow_ssh_ipv4" {
    security_group_id = aws_security_group.terraform_sg.id
    cidr_ipv4 = var.MYIP
    from_port = 22
    ip_protocol = "tcp"
    to_port = 22
}

resource "aws_vpc_security_group_ingress_rule" "allow_http_ipv4" {
    security_group_id = aws_security_group.terraform_sg.id
    cidr_ipv4 = "0.0.0.0/0"
    from_port = 80
    ip_protocol = "tcp"
    to_port = 80
}

resource "aws_vpc_security_group_ingress_rule" "allow_https_ipv4" {
    security_group_id = aws_security_group.terraform_sg.id
    cidr_ipv4 = "0.0.0.0/0"
    from_port = 443
    ip_protocol = "tcp"
    to_port = 443
}

resource "aws_vpc_security_group_ingress_rule" "allow_icmp_ipv4" {
    security_group_id = aws_security_group.terraform_sg.id
    cidr_ipv4 = "0.0.0.0/0"
    from_port = -1
    ip_protocol = "icmp"
    to_port = -1 
}

resource "aws_vpc_security_group_egress_rule" "allow_all_traffic_ipv4" {
    security_group_id = aws_security_group.terraform_sg.id
    cidr_ipv4 = "0.0.0.0/0"
    ip_protocol = "-1"
}
