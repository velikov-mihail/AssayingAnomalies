% PURPOSE: An example using scatter3dmap
%          to examine a scatter3dmap of 3 variables
%---------------------------------------------------
% USAGE: scatter3dmap_d
%---------------------------------------------------


load ohioschool.data;
long = ohioschool(:,2);
latt = ohioschool(:,3);
scores = ohioschool(:,22); % median 4th grade proficiency score
salary = ohioschool(:,9);
nonwhite = ohioschool(:,32);

scatter3dmap(long,latt,salary,nonwhite,scores,[],[],[],1); % using points
