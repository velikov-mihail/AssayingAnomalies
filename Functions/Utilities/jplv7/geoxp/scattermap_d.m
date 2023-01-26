% PURPOSE: An example using scattermap
%          to examine a scattermap of 2 variables
%---------------------------------------------------
% USAGE: scattermap_d
%---------------------------------------------------

clear all;

load ecu.data;
load ecu_xy.data;

area = ecu_xy(:,1);
latt = ecu_xy(:,2);
long = ecu_xy(:,3);

ecu95 = ecu(:,17);
ecu80 = ecu(:,2);

grwthx = ecu(:,end);

option = 2;
scattermap(long,latt,ecu80,grwthx,option,[],[],[],[],1); % using points
