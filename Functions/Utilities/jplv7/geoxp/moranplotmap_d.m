% PURPOSE: An example using moranplotmap
%          to examine the spatial dependence
%          of a vector-variable over a map
%---------------------------------------------------
% USAGE: moranplotmap_d
%---------------------------------------------------


clear all;

clear all;

load ecu.data;
load ecu_xy.data;

area = ecu_xy(:,1);
latt = ecu_xy(:,2);
long = ecu_xy(:,3);

ecu95 = ecu(:,17);
ecu80 = ecu(:,2);

grwthx = ecu(:,end);


W = make_neighborsw(latt,long,5);
flower = 1;
moranplotmap(long,latt,grwthx,W,flower,[],[],1); % using points
