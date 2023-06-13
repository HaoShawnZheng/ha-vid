from trainer import Trainer
from batch_gen import BatchGenerator
import torch
from eval import *
import sys
import os
from dataloader import VideoBoundaryDataset
import time

sys.path.append(os.path.curdir)

#os.environ["CUDA_VISIBLE_DEVICES"] = '4'
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(device)

parser = argparse.ArgumentParser()
parser.add_argument('--action', default='train')
parser.add_argument('--dataset', default="view0_lh_aa")
parser.add_argument('--split', default='1')
parser.add_argument("--date", help="today", type=str,default='0804')
parser.add_argument("--num", help="how many times do you train today? It is only used for TensorBoardX", type=str,default='1')
args = parser.parse_args()

print("Current %sing: %s, split %s" %(args.action,args.dataset,args.split))
use_saved_model=True
# in ms-tcn
use_mstcn=False # true: original MS-TCN implementation; false: our model
mstcn_use_lbp=False # just for ablation study -> MS-TCN w/ LBP
# in bcn
use_lbp=True # false: SC only; true: BCN
num_soft_lbp=1 # number of soft lbp embedded in BCN


# shared hyper-parameters
bz = 1 # batch size, currently only support 1
features_dim = 2048
num_stages = 4 # total stages for SC: num_stages-1 cascade stages and 1 fusion stage; or number of stages for MS-TCN

# lbp_post hyper-parameters for BCN or MS-TCN w/ LBP，lbp_post_length is length for resized lbp as post-processing; length for soft lbp embedded in BCN is in model.py
num_post=4  # num_post will not influence gtea because of additional if-else in trainer.py
lbp_post_length = 99

# dataset-specific hyper-parameters
if use_mstcn==False:
    #bcn
    num_layers = 12
    num_f_maps = 256
    lr = 0.001
    num_epochs = 300 #50
    test_epochs = 36

else:
    #MS-TCN hyper-parameters
    lr=0.0005
    num_layers = 10
    num_f_maps = 64
    num_epochs = 300 #50
    test_epochs = 50

# use the full temporal resolution @ 15fps
sample_rate = 1

vid_list_file = "../data/"+args.dataset+"/splits/train.split"+args.split+".bundle"
vid_list_file_tst = "../data/"+args.dataset+"/splits/test.split"+args.split+".bundle"
features_path = "../data/" + args.dataset + "/features/"
gt_path = "../data/"+args.dataset+"/groundTruth/"
mapping_file = "../data/"+args.dataset+"/mapping.txt"
model_dir = "./models/"+args.dataset+"/split_"+args.split
results_dir = "./results/"+args.dataset+"/split_"+args.split
bgm_result_path="./bgm_result/resized/bgm_output/"+args.dataset+"/"
bgm_model_path="./bgm_models/full/"+ args.dataset+"/split_"+args.split
 
if not os.path.exists(model_dir):
    os.makedirs(model_dir)
if not os.path.exists(results_dir):
    os.makedirs(results_dir)

if use_saved_model:
    model_dir = "./best_models/" + args.dataset + "/split_" + args.split
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
        
    bgm_model_path = "./best_bgm_models/full/" + args.dataset + "/split_" + args.split
    if not os.path.exists(bgm_model_path):
        os.makedirs(bgm_model_path)
    test_epochs = "best"

file_ptr = open(mapping_file, 'r')
actions = file_ptr.read().split('\n')[:-1]
file_ptr.close()
actions_dict = dict()
for a in actions:
    actions_dict[a.split()[1]] = int(a.split()[0])
num_classes = len(actions_dict)

trainer = Trainer(num_stages, num_layers, num_f_maps, features_dim, num_classes,args.dataset,device,use_lbp,num_soft_lbp)
if args.action == "train":
    start_time = time.perf_counter()
    training_time = open(results_dir+'/training_time.txt','w')
    if use_mstcn==False:
        train_loader = torch.utils.data.DataLoader(VideoBoundaryDataset(vid_list_file, num_classes, actions_dict, gt_path, features_path, sample_rate, args.dataset, device),
                                                   batch_size=bz, shuffle=True,
                                                   num_workers=2, pin_memory=True, drop_last=True)
        trainer.train_bcn(model_dir, train_loader, num_epochs, lr, device, args.date, args.num, bgm_model_path, results_dir, features_path, actions_dict, sample_rate, args.dataset,
                          vid_list_file_tst, gt_path, args.split, use_lbp, bgm_result_path, lbp_post_length, num_post=num_post)
    else:
        batch_gen = BatchGenerator(num_classes, actions_dict, gt_path, features_path, sample_rate)
        batch_gen.read_data(vid_list_file)
        trainer.train_mstcn(model_dir, batch_gen, num_epochs=num_epochs, batch_size=bz, learning_rate=lr, device=device, date=args.date, num=args.num)
    end_time = time.perf_counter()
    training_time.write('total training time: {}'.format(round(end_time-start_time)))

if args.action == "test":
    if use_mstcn==False:
        test_acc_list = open(model_dir+'/test_acc_list.txt','r')
        lines = test_acc_list.readlines()
        for line in lines:
            accs = [line[0:8] for line in lines]
        test_epochs = accs.index(max(accs))+1
        best_epoch = open(model_dir+'/best_epoch.txt','w')
        best_epoch.write(str(test_epochs))
        best_epoch.close()
        #test_epochs = lines.index(max(lines[24:])) + 1 
        trainer.predict_bcn(model_dir, results_dir, features_path, vid_list_file_tst, test_epochs, actions_dict, bgm_result_path, device, sample_rate, args.dataset, gt_path,
                            lbp_post_length, use_lbp, num_post=num_post)
        test_acc_list.close()
    else:
        trainer.predict_mstcn(model_dir, results_dir, features_path, vid_list_file_tst, test_epochs, actions_dict,device, sample_rate, bgm_result_path, mstcn_use_lbp, lbp_post_length)
