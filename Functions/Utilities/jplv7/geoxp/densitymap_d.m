% PURPOSE: An example using densitymap
%          to examine the density of
%          a vector-variable over a map
%---------------------------------------------------
% USAGE: densitymap_d
%---------------------------------------------------


clear all;

load('matADTCAN.txt');
carte = matADTCAN;
[xy,txt] = WK1READ('codecoord2.wk1');
long = xy(2:end,2);
latt = xy(2:end,3);
docs = xy(2:end,1);

densitymap(latt,long,docs,50,carte,[],1); % using map polygons

