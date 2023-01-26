% PURPOSE: An example using sirmap
%          to examine the sliced inverse regression models
%          by selecting sub-samples using a map
%---------------------------------------------------
% USAGE: sirmap_d
%---------------------------------------------------


clear all;

load ecu.data;
load ecu_xy.data;

area = ecu_xy(:,1);
latt = ecu_xy(:,2);
long = ecu_xy(:,3);
W = make_neighborsw(latt,long,5);

ecu95 = ecu(:,17);
ecu80 = ecu(:,2);

grwthx = ecu(:,end);
n = length(grwthx);

xmat = [log(ecu80) W*log(ecu80)];
nclasses = 3;
sirmap(long,latt,xmat,grwthx,nclasses,[],[],[],1);
