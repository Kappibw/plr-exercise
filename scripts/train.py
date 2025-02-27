from __future__ import print_function
import argparse
import torch
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torch.optim.lr_scheduler import StepLR
from plr_exercise.models import Net
from plr_exercise import PLR_ROOT_DIR
import wandb
import os
import optuna


def train(args, model, device, train_loader, optimizer, epoch):
    """Train an epoch of the model

    Args:
        args (any): Command line args
        model (torch.nn): Torch model
        device (torch.device): cuda or cpu
        train_loader (any): loader
        optimizer (any): optimizer
        epoch (int): Current epoch
    """
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):

        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            print(
                "Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}".format(
                    epoch,
                    batch_idx * len(data),
                    len(train_loader.dataset),
                    100.0 * batch_idx / len(train_loader),
                    loss.item(),
                )
            )
            wandb.log({"epoch": epoch, "train_loss": loss.item()})
            if args.dry_run:
                break


def test(model, device, test_loader, epoch):
    """Test the model at current epoch

    Args:
        model (Torch.nn): Model to test
        device (torch.device): cuda or cpu
        test_loader (any): loader
        epoch (int): current epoch

    Returns:
        float: test loss
    """
    model.eval()
    test_loss = 0
    correct = 0

    with torch.no_grad():
        for data, target in test_loader:

            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction="sum").item()  # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)

    print(
        "\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n".format(
            test_loss, correct, len(test_loader.dataset), 100.0 * correct / len(test_loader.dataset)
        )
    )
    wandb.log({"test_loss": test_loss, "epoch": epoch})
    return test_loss


def main():
    """run the training of the model

    Trains the cnn model and does a hyperparam sweep
    """
    # Training settings
    parser = argparse.ArgumentParser(description="PyTorch MNIST Example")
    parser.add_argument(
        "--batch-size", type=int, default=64, metavar="N", help="input batch size for training (default: 64)"
    )
    parser.add_argument(
        "--test-batch-size", type=int, default=1000, metavar="N", help="input batch size for testing (default: 1000)"
    )
    parser.add_argument("--epochs", type=int, default=2, metavar="N", help="number of epochs to train (default: 14)")
    # parser.add_argument("--lr", type=float, default=1.0, metavar="LR", help="learning rate (default: 1.0)")
    parser.add_argument("--gamma", type=float, default=0.7, metavar="M", help="Learning rate step gamma (default: 0.7)")
    parser.add_argument("--no-cuda", action="store_true", default=False, help="disables CUDA training")
    parser.add_argument("--dry-run", action="store_true", default=False, help="quickly check a single pass")
    parser.add_argument("--seed", type=int, default=1, metavar="S", help="random seed (default: 1)")
    parser.add_argument(
        "--log-interval",
        type=int,
        default=10,
        metavar="N",
        help="how many batches to wait before logging training status",
    )
    parser.add_argument("--save-model", action="store_true", default=False, help="For Saving the current Model")
    args = parser.parse_args()

    wandb.login()
    os.makedirs(os.path.join(PLR_ROOT_DIR, "results"), exist_ok=True)
    run = wandb.init(
        dir=os.path.join(PLR_ROOT_DIR, "results"),
        project="plr-project",
        config=args,
        settings=wandb.Settings(code_dir=PLR_ROOT_DIR),
    )
    include_fn = lambda path, root: path.endswith(".py") or path.endswith(".yaml")
    run.log_code(name="source_files", root=PLR_ROOT_DIR, include_fn=include_fn)

    use_cuda = not args.no_cuda and torch.cuda.is_available()

    torch.manual_seed(args.seed)

    if use_cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    train_kwargs = {"batch_size": args.batch_size}
    test_kwargs = {"batch_size": args.test_batch_size}
    if use_cuda:
        cuda_kwargs = {"num_workers": 1, "pin_memory": True, "shuffle": True}
        train_kwargs.update(cuda_kwargs)
        test_kwargs.update(cuda_kwargs)
    transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))])
    dataset1 = datasets.MNIST("../data", train=True, download=True, transform=transform)
    dataset2 = datasets.MNIST("../data", train=False, transform=transform)
    train_loader = torch.utils.data.DataLoader(dataset1, **train_kwargs)
    test_loader = torch.utils.data.DataLoader(dataset2, **test_kwargs)

    def objective(trial):
        # Optuna variables
        lr = trial.suggest_float("lr", 1e-4, 1e-1, log=True)
        # epochs = trial.suggest_int("epochs", 1, 3)
        gamma = trial.suggest_float("gamma", 0.5, 0.9)

        model = Net().to(device)
        optimizer = optim.Adam(model.parameters(), lr=lr)
        scheduler = StepLR(optimizer, step_size=1, gamma=gamma)

        # Training loop
        for epoch in range(args.epochs):
            train(args, model, device, train_loader, optimizer, epoch)
            test_loss = test(model, device, test_loader, epoch)
            scheduler.step()

        return test_loss

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=5)

    # Save or print the best hyperparameters
    print("Best trial:")
    trial = study.best_trial
    print(f"  Value: {trial.value}")
    print("  Params: ")
    for key, value in trial.params.items():
        print(f"    {key}: {value}")

    # if args.save_model:
    #     torch.save(model.state_dict(), "mnist_cnn.pt")

    wandb.finish()


if __name__ == "__main__":
    main()
