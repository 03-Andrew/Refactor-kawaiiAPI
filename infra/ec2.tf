resource "aws_key_pair" "booking_key" {
  key_name   = "booking-ec2-key"
  public_key = pathexpand("~/.ssh/id_ed25519.pub") # Only public key enters state
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
    instance_type = "t3.micro"
    subnet_id = aws_subnet.public_booking_subnet_1.id
    key_name = aws_key_pair.booking_key.key_name
    vpc_security_group_ids = [aws_security_group.terraform_sg.id]
    user_data = file("${path.module}/user_data.sh")
    tags = {
        Name = "booking-ec2-instance"
    }
}

resource "aws_eip" "booking-eip" {
    instance = aws_instance.booking-ec2-instance.id    
    domain = "vpc"
}
