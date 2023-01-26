% PURPOSE: An example using scattermap
%          to examine a scattermap of 2 variables
%---------------------------------------------------
% USAGE: clustermap_d
%---------------------------------------------------

% PURPOSE: An example using clustermap
%          to examine a matrix of variables
%          by clusters over a map
%---------------------------------------------------
% USAGE: clustermap_d
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

clusters = 4;
method = 1;

clustermap(long,latt,[ecu80 ecu95 grwthx],clusters,method); % using points

% clustermap(long,latt,[ecu80 ecu95 grwthx],clusters,method,[],[],1); % using symbols
