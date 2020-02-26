"""this is main program of segnet with kmeans(use one trajectory)"""
#!/usr/bin/env python
# coding: utf-8
# conda envs==py35

import argparse
import time
import os
import numpy as np
import pandas as pd
import torch

from my_util import get_traj, plt_label, set_hypara, sec_argmax, Args
from my_util import do_kmeans_InsteadOfSlic, utils, analyze_segmentation

import matplotlib.pyplot as plt

### begin region ###

import logging

# create logger
logger = logging.getLogger('train_model')
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
sh = logging.StreamHandler()
fh = logging.FileHandler("./log/test.log")
sh.setLevel(logging.INFO)
fh.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('[%(asctime)s] - [%(name)s] - [%(levelname)s] - %(message)s')

# add formatter to handler
sh.setFormatter(formatter)
fh.setFormatter(formatter)

# add handler to logger
logger.addHandler(sh)
logger.addHandler(fh)

### end region ###

device = torch.device("cuda" if torch.cuda.is_available() else 'cpu')

def run(traj, len_traj, args, model, optimizer, number_traj, epoch):
    """
    Run algorithm at each trajectory
        traj        :   [np.array]      :   train data and reshape into tensor
        len_traj    :   [int]           :   len of traj without None
        args        :   [class]         :   hyper params
        model       :   [model]         :
        optimizer   :   [optimizer]     :
    """

    def reshape_train_data(traj):
        # reshape
        tensor = traj.transpose((2, 0, 1))
        # float
        tensor = tensor.astype(np.float32)
        # reshape
        tensor = tensor[np.newaxis, :, :, :]
        tensor = torch.from_numpy(tensor).to(device)
        return tensor

    logger.debug("start segmentation:")

    # TODO:遅いので，事前に全軌跡のKmeansを算出，保存しといて，参照だけにする
    ret_seg_map = do_kmeans_InsteadOfSlic.handle_kmeans(\
        k=int(len_traj/4), traj=traj, window=args.window, time_dim=args.time_dim)

    #logger.debug("ret_seg_map: %s" % (ret_seg_map))

    seg_map = ret_seg_map.flatten()
    seg_lab = [np.where(seg_map == u_label)[0] for u_label in np.unique(seg_map)]

    logger.debug("end segmentation:")

    tensor = reshape_train_data(traj)

    '''train loop'''

    model.train()

    # loss every batch, num of
    ret_loss = []
    ls_target_idx = []

    for BATCH_IDX in range(args.train_epoch):

        '''forward'''
        optimizer.zero_grad()
        output = model(tensor)
        output = output[0]
        output = output.permute(1, 2, 0).view(-1, args.mod_dim2)
        target = torch.argmax(output, 1)

        if args.sec_argmax:
            target_idx = sec_argmax.get_idx_samelabel(target)
            target = sec_argmax.get_argsecmax(output, target, target_idx, BATCH_IDX)

        plt_label.plot_entropy_at_each_pixel(output, BATCH_IDX, args, "output")

        im_target = target.data.cpu().numpy()

        """refine"""
        for inds in seg_lab:
            u_labels, hist = np.unique(im_target[inds], return_counts=True)
            im_target[inds] = u_labels[np.argmax(hist)]

        """backward"""
        target = torch.from_numpy(im_target)
        target = target.to(device)

        """get loss"""
        loss = utils.set_loss_functtion(output=output, target=target, args=args)
        loss.backward()
        optimizer.step()

        un_label = np.unique(im_target, )

        ret_loss.append(loss.item())

        logger.debug("Trajectory epoch: %d/%d, loss: %1.5f" % \
            (BATCH_IDX, args.train_epoch, loss.item()))

        if args.sec_argmax:
            ls_target_idx.extend([len(target_idx)])

        if len(un_label) < args.MIN_LABEL_NUM:
            break
        
        #plt_label.plot_entropy_at_each_batch(output, traj, len_traj, args, BATCH_IDX)

    plt_label.save_gif(args, number_traj, epoch)

    return im_target, ret_loss

def train(args, traj, model, optimizer):

    def reshape_traj(i):
        traj_ = traj[:, i, :]
        traj_ = traj_[~np.isnan(traj_).any(axis=1)]
        traj_ = traj_[:, np.newaxis, :]
        return traj_

    def get_latlon(i):
        lat_i = pd.DataFrame(traj[:, i, 0]).dropna(how="all")
        lat_i = lat_i.reset_index(drop=True)
        lon_i = pd.DataFrame(traj[:, i, 1]).dropna(how="all")
        lon_i = lon_i.reset_index(drop=True)
        return lat_i, lon_i

    loss_all = []

    for e in range(args.epoch_all):

        logger.info("Train epoch: %d/%d " % (e + 1, args.epoch_all))

        for i in range(args.START_ID, args.END_ID):

            logger.debug("Trajectory Num: %d/%d" % (i - args.START_ID, args.END_ID - args.START_ID))

            traj_ = reshape_traj(i)

            if traj_.shape[0] < 10:
                # assert(ValueError("Too short data"))
                continue

            """get lat, lon for plot only kmeans"""
            lat_i, lon_i = get_latlon(i)
            #plt_label.plot_only_kmeans(traj_, lat_i, lon_i, args, e)

            """ run """
            length_traj_ = lat_i.shape[0]
            label, loss = run(traj_, length_traj_, args, model, optimizer, i, e)
            loss_all.extend(loss)

            """plot result seg"""
            analyze_segmentation.plot_relabel(label, lat_i, lon_i, \
                args.animal, args.result_dir, i, e)

        analyze_segmentation.analyze(label, args.animal, args.result_dir, i, e)

        torch.save(label, "result/{}/trip{:0=3}.pkl".format(args.result_dir, i))

    torch.save(model.state_dict(), "./models/model.pkl")

    plt.plot(loss_all)
    plt.ylabel("loss")
    plt.xlabel("batches")
    plt.title("loss")
    plt.savefig("./result/" + args.result_dir + "/loss.png")

def load_data(args):
    """preprocessed data"""
    if os.path.exists(get_traj.animal_path(args.animal)):
        logger.debug("Load df")
        df_trajectory = get_traj.load_traj(args.animal)
        df_trajectory = get_traj.norm_traj(df_trajectory)
    else:
        logger.debug("Make df, Save")
        df_trajectory = get_traj.get_traj(args.lat, args.lon, args.animal)
        get_traj.save_traj(args.animal, df_trajectory)
    #df_trajectory = df_trajectory.fillna(0)

    """reshape data"""
    traj = df_trajectory.values
    traj = np.reshape(traj, (traj.shape[0], int(traj.shape[1]/3), 3))
    return traj

def main(args):
    """do trian(), run() and plot results for all trajectory"""

    torch.cuda.manual_seed_all(1943)
    np.random.seed(1943)
    os.environ['CUDA_VISIBLE_DEVICES'] = str(args.GPU_ID)

    traj = load_data(args)

    model = utils.set_network_model(network=args.network,\
        mod_dim1=args.mod_dim1, mod_dim2=args.mod_dim2, device=device)

    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)

    train(args, traj, model, optimizer)

if __name__ == '__main__':
    PARSER = argparse.ArgumentParser(description="this is Segnet with Kmeans")

    # data
    PARSER.add_argument("--animal", choices=["cel", "bird"], default="bird")

    # train
    PARSER.add_argument("-e", "--epoch", type=int, default=2**5, help="BATCH: num of trainging with one trajectory")
    PARSER.add_argument("--epoch_all", type=int, default=2**3, help="EPOCH: num of training with all trajectories")

    # hypara of custom loss
    PARSER.add_argument("--alpha", type=float, default=10, help="to be bigger, enlarge d. To be smaller, ensmaller d")
    PARSER.add_argument("--lambda_p", type=float, default=0.01)
    PARSER.add_argument("--tau", type=float, default=100, help="to be smaller, enlarge w.")

    # on/off custom module
    PARSER.add_argument("--time", action="store_true")
    PARSER.add_argument("--myloss", action="store_false")
    PARSER.add_argument("--secmax", action="store_true")

    # set traj id
    PARSER.add_argument("--start", type=int, default=0, help="this is start_id")
    PARSER.add_argument("--end", type=int, default=5, help="this is end_id")

    # select network
    PARSER.add_argument("--net", type=str, default="segnet")

    # train high param
    PARSER.add_argument("--lr", type=float, default=0.05, help="learing rate")
    PARSER.add_argument("--momentum", type=float, default=0.9, help="learing rate")

    ARGS_TMP = PARSER.parse_args()
    ARGSE = Args()

    # HACK: this is too uneffectively.
    # translate from input arg to default arg
    ARGSE = set_hypara.set_hypara(ARGSE, ARGS_TMP)

    logger.info("Train Start")

    main(ARGSE)

    logger.info("Train End")
