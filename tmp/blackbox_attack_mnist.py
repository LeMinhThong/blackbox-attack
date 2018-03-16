import time
import random 
import numpy as np
import torch 
import torch.nn as nn
import torchvision.datasets as dsets
import torchvision.transforms as transforms
from torch.autograd import Variable

import torch.nn.functional as F

# Hyperparameters
num_epochs = 50
batch_size = 128
learning_rate = 0.001

alpha = 0.018
beta = 0.05

def show(img):
    """
    Show MNSIT digits in the console.
    """
    remap = "  .*#"+"#"*100
    img = (img.flatten()+.5)*3
    if len(img) != 784: return
    for i in range(28):
        print("".join([remap[int(round(x))] for x in img[i*28:i*28+28]]))


def load_data():
    """ Load MNIST data from torchvision.datasets 
        input: None
        output: minibatches of train and test sets 
    """
    # MNIST Dataset
    train_dataset = dsets.MNIST(root='./mnist/', train=True, transform=transforms.ToTensor(), download=True)
    test_dataset = dsets.MNIST(root='./mnist/', train=False, transform=transforms.ToTensor())
    #transform_train = tfs.Compose([
    #    tfs.RandomCrop(32, padding=4),
    #    tfs.RandomHorizontalFlip(),
    #    tfs.ToTensor()
    #    ])
 
    #train_dataset = dsets.CIFAR10('./cifar10-py', download=False, train=True, transform= transforms.ToTensor())
    #test_dataset = dsets.CIFAR10('./cifar10-py', download=False, train=False, transform= transforms.ToTensor())

    
    
    # Data Loader (Input Pipeline)
    train_loader = torch.utils.data.DataLoader(dataset=train_dataset, batch_size=batch_size, shuffle=True, num_workers=2)
    test_loader = torch.utils.data.DataLoader(dataset=test_dataset, batch_size=batch_size, shuffle=False, num_workers=2)
    return train_loader, test_loader, train_dataset, test_dataset


class CNN(nn.Module):
    def __init__(self):
        super(CNN, self).__init__()
        self.features = self._make_layers()
        self.fc1 = nn.Linear(1024,200)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(200,200)
        self.dropout = nn.Dropout(p=0.5)
        self.fc3 = nn.Linear(200,10)

    def forward(self, x):
        out = self.features(x)
        out = out.view(out.size(0), -1)
        out = self.fc1(out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc3(out)
        return out

    def _make_layers(self):
        layers=[]
        in_channels= 1
        layers += [nn.Conv2d(in_channels, 32, kernel_size=3),
                   nn.BatchNorm2d(32),
                   nn.ReLU()]
        layers += [nn.Conv2d(32, 32, kernel_size=3),
                   nn.BatchNorm2d(32),
                   nn.ReLU()]
        layers += [nn.MaxPool2d(kernel_size=2, stride=2)]
        layers += [nn.Conv2d(32, 64, kernel_size=3),
                   nn.BatchNorm2d(64),
                   nn.ReLU()]
        layers += [nn.Conv2d(64, 64, kernel_size=3),
                   nn.BatchNorm2d(64),
                   nn.ReLU()]
        layers += [nn.MaxPool2d(kernel_size=2, stride=2)]
        
        return nn.Sequential(*layers)


    def predict(self, image):
        self.eval()
        image = Variable(image).view(1,1,28,28)
        output = self(image)
        _, predict = torch.max(output.data, 1)
        return predict[0]

   

def train(model, train_loader):
    # Loss and Optimizer
    model.train()
    lr = 0.01
    momentum = 0.9
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=lr, momentum=momentum, nesterov=True)
    # Train the Model
    for epoch in range(num_epochs):
        for i, (images, labels) in enumerate(train_loader):
            optimizer.zero_grad()
            images = Variable(images)
            labels = Variable(labels)
        
            # Forward + Backward + Optimize
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
        
            if (i+1) % 100 == 0:
                print ('Epoch [%d/%d], Iter [%d] Loss: %.4f' 
                    %(epoch+1, num_epochs, i+1, loss.data[0]))

def test(model, test_loader):
    # Test the Model
    model.eval()  # Change model to 'eval' mode (BN uses moving mean/var).
    correct = 0
    total = 0
    for images, labels in test_loader:
        images = Variable(images)
        outputs = model(images)
        _, predicted = torch.max(outputs.data, 1)
        total += labels.size(0)
        correct += (predicted == labels).sum()

    print('Test Accuracy of the model on the 10000 test images: %.2f %%' % (100.0 * correct / total))

def save_model(model, filename):
    """ Save the trained model """
    torch.save(model.state_dict(), filename)

def load_model(model, filename):
    """ Load the training model """
    model.load_state_dict(torch.load(filename))

def attack(model, train_dataset, x0, y0, alpha = 0.018, beta = 0.05, query_limit = 100000):
    """ Attack the original image and return adversarial example"""

    if (model.predict(x0) != y0):
        print("Fail to classify the image. No need to attack.")
        return x0

    num_samples = 20 
    best_theta = None
    best_distortion = float('inf')
    g_theta = None
    query_search_each = 100
    query_count = 0
    print("Searching for the initial direction on %d samples: " % (num_samples))

    timestart = time.time()
    samples = set(random.sample(range(len(train_dataset)), num_samples))
    for i, (xi, yi) in enumerate(train_dataset):
        if i not in samples:
            continue
        query_count += 1
        if model.predict(xi) != y0:
            theta = xi - x0
            query_count += query_search_each
            lbd = fine_grained_binary_search(model, x0, y0, theta, query_limit = query_search_each)
            distortion = torch.norm(lbd*theta)
            if distortion < best_distortion:
                best_theta, g_theta = theta, lbd
                best_distortion = distortion
                print("--------> Found distortion %.4f and g_theta = %.4f" % (best_distortion, g_theta))

    timeend = time.time()
    print("==========> Found best distortion %.4f and g_theta = %.4f in %.4f seconds" % (best_distortion, g_theta, timeend-timestart))

    query_limit -= query_count

  
    timestart = time.time()

    query_search_each = 200  # limit for each lambda search
    iterations = (query_limit - query_search_each)//(2*query_search_each)
    g1 = 1.0
    g2 = g_theta
    theta = best_theta

    for i in range(iterations):
        u = torch.randn(theta.size()).type(torch.FloatTensor)
        g1 = fine_grained_binary_search(model, x0, y0, theta + beta * u, initial_lbd = g1, query_limit = query_search_each)
        g2 = fine_grained_binary_search(model, x0, y0, theta, initial_lbd = g2, query_limit = query_search_each)
        if g1 == float('inf'):
            print("WHY g1???")
        if g2 == float('inf'):
            print("WHY g2???")
        if (i+1)%50 == 0:
            print("Iteration %3d: g(theta + beta*u) = %.4f g(theta) = %.4f distortion %.4f" % (i+1, g1, g2, torch.norm(g2*theta)))
        gradient = (g1-g2)/beta * u
        theta.sub_(alpha*gradient)

    g2 = fine_grained_binary_search(model, x0, y0, theta, initial_lbd = g2, query_limit = query_search_each)
    distortion = torch.norm(g2*theta)
    target = model.predict(x0 + g2*theta)
    timeend = time.time()
    print("\nAdversarial Example Found Successfully: distortion %.4f target %d \nTime: %.4f seconds" % (distortion, target, timeend-timestart))
    return x0 + g2*theta

def fine_grained_binary_search(model, x0, y0, theta, initial_lbd = 1.0, query_limit = 200):
    lbd = initial_lbd
    while model.predict(x0 + lbd*theta) == y0:
        lbd *= 2.0
        query_limit -= 1

    if lbd > 1000 or query_limit < 0:
        print("WHY lbd > 1000")
        return float('inf')

    # fine-grained search 
    query_fine_grained = query_limit - 10
    query_binary_search = 10

    lambdas = np.linspace(lbd, 0.0, query_fine_grained)[1:]
    lbd_hi = lbd
    lbd_hi_index = 0
    for i, lbd in enumerate(lambdas):
        if model.predict(x0 + lbd*theta) != y0:
            lbd_hi = lbd
            lbd_hi_index = i

    lbd_lo = lambdas[lbd_hi_index - 1]

    while query_binary_search > 0:
        lbd_mid = (lbd_lo + lbd_hi)/2.0
        if model.predict(x0 + lbd_mid*theta) != y0:
            lbd_hi = lbd_mid
        else:
            lbd_lo = lbd_mid
        query_binary_search -= 1
    
    return lbd_hi

def main():
    train_loader, test_loader, train_dataset, test_dataset = load_data()
    net = CNN()
    #train(net, train_loader)
    load_model(net, 'models/mnist.pt')
    test(net, test_loader)
    #save_model(net,'./models/mnist.pt')
    net.eval()

    query_limit = 100000

    num_images = 1

    for i, (image, label) in enumerate(test_dataset):
        if i >= num_images:
            break
        print("\n\n\n\n======== Image %d =========" % i)
        show(image.numpy())
        print("Original label: ", label)
        print("Predicted label: ", net.predict(image))
        adversarial = attack(net, train_dataset, image, label, alpha = alpha, beta = beta, query_limit = query_limit)
        show(adversarial.numpy())
        print("Predicted label for adversarial example: ", net.predict(adversarial))
        #print("mindist: ", mindist)
        #print(theta)

    print("\n\n\n\n\n Random Sample\n\n\n")

    for _ in range(num_images):
        idx = random.randint(100, len(test_dataset)-1)
        image, label = test_dataset[idx]
        print("\n\n\n\n======== Image %d =========" % idx)
        show(image.numpy())
        print("Original label: ", label)
        print("Predicted label: ", net.predict(image))
        adversarial = attack(net, train_dataset, image, label, alpha = alpha, beta = beta, query_limit = query_limit)
        show(adversarial.numpy())
        print("Predicted label for adversarial example: ", net.predict(adversarial))


if __name__ == '__main__':
    timestart = time.time()
    main()
    timeend = time.time()
    print("\n\nTotal running time: %.4f seconds\n" % (timeend - timestart))

    # estimate time per one iteration (two examples)
    # query = 100000 -> 149 seconds
    # query = 500000 ->  
    # query = 1000000 ->  
