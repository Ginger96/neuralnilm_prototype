from __future__ import print_function, division
import os


def run_experiment(net, path):
    net.print_net()
    net.compile()
    try:
        os.mkdir(path)
    except OSError as exception:
        if exception.errno == 17:
            print(path, "already exists.  Reusing directory.")
        else:
            raise
    os.chdir(path)
    fit(net)


def fit(net, epochs=1500):
    print("Running net.fit for", net.experiment_name)
    save_plots = "y"
    continue_fit = "n"
    try:
        net.fit(epochs)
    except KeyboardInterrupt:
        print("Keyboard interrupt received.")
        enter_debugger = raw_input("Enter debugger [N/y]? ")
        if enter_debugger.lower() == 'y':
            import ipdb; ipdb.set_trace()
        save_plots = raw_input("Save latest data [Y/n]? ")
        stop_all = raw_input("Stop all experiments [Y/n]? ")
        if not stop_all or stop_all.lower() == "y":
            raise
        continue_fit = raw_input("Continue fitting this experiment [N/y]? ")
    finally:
        if not save_plots or save_plots.lower() == "y":
            print("Saving plots...")
            net.plot_estimates(save=True, all_sequences=True)
            net.plot_costs(save=True)
            print("Saving params...")
            net.save_params()
            print("Done saving.")

    if continue_fit == "y":
        new_epochs = raw_input("Change number of epochs [currently {}]? "
                               .format(epochs))
        if new_epochs:
            epochs = int(new_epochs)
        fit(net, epochs)