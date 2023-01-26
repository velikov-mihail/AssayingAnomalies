% PURPOSE: An example using variocloudmap
%          to examine the scatter of a
%          variable using a map
%---------------------------------------------------
% USAGE: variocloudmap_d
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

robust = 0;
opt = 2;
variocloudmap(long,latt,grwthx,robust,opt,[],[],[],1);
