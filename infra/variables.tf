
variable "REGION" {
  default = "ap-southeast-1"
}

variable "ZONE1" {
  default = "ap-southeast-1a"
}

variable "ZONE2" {
  default = "ap-southeast-1b"
}

variable "MYIP" {
  type = string
}

variable "PASSWORD" {
  type = string
}

variable "USER" {
  default = "ubuntu"
}

variable "PUB_KEY" {
  default = "YOUR_KEY"
}