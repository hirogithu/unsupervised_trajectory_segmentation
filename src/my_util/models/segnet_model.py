"""segnet model"""
import torch.nn as nn

class MyNet(nn.Module):
    """this is neural net module"""
    def __init__(self, inp_dim, mod_dim1, mod_dim2):
        super(MyNet, self).__init__()

        pad = (0, 0, 2, 2)

        self.seq = nn.Sequential(
            nn.Conv2d(inp_dim, mod_dim1, kernel_size=(5, 1), stride=1, padding=0),
            nn.BatchNorm2d(mod_dim1),
            nn.ReLU(inplace=True),

            nn.ConstantPad2d(pad, 0),

            nn.Conv2d(mod_dim1, mod_dim2, kernel_size=(1, 1), stride=1, padding=0),
            nn.BatchNorm2d(mod_dim2),
            nn.ReLU(inplace=True),

            nn.Conv2d(mod_dim2, mod_dim1, kernel_size=(5, 1), stride=1, padding=0),
            nn.BatchNorm2d(mod_dim1),
            nn.ReLU(inplace=True),

            nn.ConstantPad2d(pad, 0),

            nn.Conv2d(mod_dim1, mod_dim2, kernel_size=(1, 1), stride=1, padding=0),
            nn.BatchNorm2d(mod_dim2),
        )

    def forward(self, x):
        #print(x.shape)
        return self.seq(x)
