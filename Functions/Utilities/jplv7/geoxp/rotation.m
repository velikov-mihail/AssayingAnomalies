function nellecoord=rotation(coord,angle)
% PURPOSE : This function rotates objects of spatial coordinates type
%------------------------------------------------------------------------------
% USAGE : rotationmim(coord,angle) 
%    where : coord : (n x 2) matrix of coordinates
%            angle : angle of the rotation in degree
%------------------------------------------------------------------------------
%  OUTPUTS :  new coordinates after rotation
%------------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr

radian=(angle * pi)/180;
x=[cos(radian) sin(radian)];
y=[- sin(radian) cos(radian)];
nellecoord=coord * cat(1,x,y);
