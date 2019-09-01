variable "location" {
  description = "Datacenter location to deploy the VM into"
  default     = "westus2"
}

variable "vm_name" {
  description = "Name of the virtual machine (acts as prefix for all generated resources)"
  default     = "annotation-vm"
}

variable "vm_type" {
  description = "The type of VM to deploy"
  default     = "Standard_D4s_v3"
}

variable "admin_user" {
  description = "Admin username"
  default     = "root"
}

variable "admin_public_key" {
  description = "Path to Public SSH key of the admin user"
  default     = "~/.ssh/id_rsa.pub"
}

variable "admin_private_key" {
  description = "Path to Private SSH key of the admin user"
  default     = "~/.ssh/id_rsa"
}

resource "azurerm_resource_group" "ds" {
  name     = var.vm_name
  location = var.location
}

resource "azurerm_virtual_network" "ds" {
  name                = "${var.vm_name}-network"
  address_space       = ["10.0.0.0/15"] # was 16 instead of 15
  location            = azurerm_resource_group.ds.location
  resource_group_name = azurerm_resource_group.ds.name
}

resource "azurerm_subnet" "ds" {
  name                 = "${var.vm_name}-subnet"
  resource_group_name  = azurerm_resource_group.ds.name
  virtual_network_name = azurerm_virtual_network.ds.name
  address_prefix       = "10.0.2.0/23" # was 24 instead of 23
}

resource "azurerm_network_interface" "ds" {
  name                = "${var.vm_name}-ni"
  location            = azurerm_resource_group.ds.location
  resource_group_name = azurerm_resource_group.ds.name

  ip_configuration {
    name                          = "${var.vm_name}-cfg"
    subnet_id                     = azurerm_subnet.ds.id
    private_ip_address_allocation = "dynamic"
    public_ip_address_id          = azurerm_public_ip.ds.id
  }
}

resource "azurerm_virtual_machine" "ds" {
  name                             = "${var.vm_name}-vm"
  location                         = azurerm_resource_group.ds.location
  resource_group_name              = azurerm_resource_group.ds.name
  network_interface_ids            = [azurerm_network_interface.ds.id]
  vm_size                          = var.vm_type
  delete_os_disk_on_termination    = true
  delete_data_disks_on_termination = true

  storage_image_reference {
    publisher = "Canonical"
    offer     = "UbuntuServer"
    sku       = "16.04.0-LTS"
    version   = "latest"
  }

  storage_os_disk {
    name              = "${var.vm_name}-osdisk"
    caching           = "ReadWrite"
    create_option     = "FromImage"
    managed_disk_type = "Standard_LRS"
  }

  os_profile {
    computer_name  = var.vm_name
    admin_username = var.admin_user
  }

  os_profile_linux_config {
    disable_password_authentication = true

    ssh_keys {
      path     = "/home/${var.admin_user}/.ssh/authorized_keys"
      key_data = file(var.admin_public_key)
    }
  }

  tags = {
    environment = "annotation-vm, ${var.vm_name}"
  }

  provisioner "remote-exec" {
    inline = [
      "git clone https://github.com/ecohydro/coco-annotator",
      "sudo curl -L "https://github.com/docker/compose/releases/download/1.24.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose",
      "sudo chmod +x /usr/local/bin/docker-compose",
      "newgrp docker",
      "cd coco-annotator && docker-compose up", # starts server at port 5000
      "sudo mkdir -p /permmnt/cropmaskperm" # for mounting permanently after stopping and starting. use connect button in portal to get sh command to mount
    ]

    connection {
      type        = "ssh"
      user        = var.admin_user
      private_key = file(var.admin_private_key)
      host        = azurerm_public_ip.ds.ip_address
    }
  }
}

# create a public IP to bind against the VM
resource "azurerm_public_ip" "ds" {
  name                         = "${var.vm_name}-ip"
  location                     = azurerm_resource_group.ds.location
  resource_group_name          = azurerm_resource_group.ds.name
  public_ip_address_allocation = "static"

  tags = {
    environment = "datascience-vm, ${var.vm_name}"
  }
}

# dump reference to public IP and VM ID to local files; if anything changes just re-run terraform apply to re-generate the files locally
resource "null_resource" "ds" {
  triggers = {
    vm_id      = azurerm_virtual_machine.ds.id
    ip_address = azurerm_public_ip.ds.ip_address
  }

  provisioner "local-exec" {
    command = "echo ${azurerm_virtual_machine.ds.id} > .vm-id-annotation"
  }

  provisioner "local-exec" {
    command = "echo ${var.admin_user}@${azurerm_public_ip.ds.ip_address} > .vm-ip-annotation"
  }

    connection {
      type        = "ssh"
      user        = var.admin_user
      private_key = file(var.admin_private_key)
      host        = azurerm_public_ip.ds.ip_address
    }
  }


