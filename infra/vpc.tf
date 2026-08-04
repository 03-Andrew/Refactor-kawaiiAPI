resource "aws_vpc" "booking_vpc" {
    cidr_block = "10.0.0.0/16"
    instance_tenancy = "default"
    enable_dns_support = "true"
    enable_dns_hostnames = "true"
    tags = {
        Name = "booking_vpc"
    }
}

resource "aws_subnet" "public_booking_subnet_1" {
    vpc_id = aws_vpc.booking_vpc.id
    cidr_block = "10.0.1.0/24"
    map_public_ip_on_launch = "true"
    availability_zone = var.ZONE1
    tags = {
        Name = "public_booking_subnet_1"
    } 
}

resource "aws_subnet" "private_booking_subnet_1" {
    vpc_id = aws_vpc.booking_vpc.id
    cidr_block = "10.0.2.0/24"
    availability_zone = var.ZONE1
    tags = {
        Name = "private_booking_subnet_1"
    }   
}

resource "aws_subnet" "private_booking_subnet_2" {
    vpc_id = aws_vpc.booking_vpc.id
    cidr_block = "10.0.3.0/24"
    availability_zone = var.ZONE2
    tags = {
        Name = "private_booking_subnet_2"
    }   
}

resource "aws_internet_gateway" "booking_IGW" {
    vpc_id = aws_vpc.booking_vpc.id
    tags = {
        Name = "booking_IGW"
    }
}

resource "aws_route_table" "public_booking_RT" {
    vpc_id = aws_vpc.booking_vpc.id
    tags = {
        Name = "public_booking_RT"
    }
}

resource "aws_route" "internet_access" {
    route_table_id = aws_route_table.public_booking_RT.id
    destination_cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.booking_IGW.id
}

resource "aws_route_table_association" "public_booking_subnet_1a" {
    subnet_id = aws_subnet.public_booking_subnet_1.id
    route_table_id = aws_route_table.public_booking_RT.id
}


