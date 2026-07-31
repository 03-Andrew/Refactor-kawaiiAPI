resource "aws_key_pair" "booking_key" {
  key_name   = "booking-ec2-key"
  public_key = file("~/.ssh/id_ed25519.pub") # Only public key enters state
}

data "aws_ami" "ubuntu" {
    most_recent = true
    filter {
        name = "name"
        values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
    }
    owners = ["099720109477"] # Canonical
}

resource "aws_instance" "booking-ec2-instance" {
    ami = data.aws_ami.ubuntu.id
    instance_type = "t3.nano"
    subnet_id = aws_subnet.public_booking_subnet_1.id
    key_name = aws_key_pair.booking_key.key_name
    vpc_security_group_ids = [aws_security_group.terraform_sg.id]
    tags = {
        Name = "booking-ec2-instance"
    }
}

output "PublicIP" {
    value = aws_instance.booking-ec2-instance.public_ip
}